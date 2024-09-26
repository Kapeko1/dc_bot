import discord
from discord.ext import commands, tasks
import aiohttp  # Use aiohttp for asynchronous HTTP requests

# Replace with your bot token
BOT_TOKEN = ''
# Channel ID where updates will be sent
CHANNEL_ID = 1286326334188028087

# Create an instance of Intents
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content (for commands)

# Create a bot instance with command prefix and intents
bot = commands.Bot(command_prefix='/', intents=intents)

# Dictionary to keep track of player IDs and their kills
player_kills = {}
player_ids = set()


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    track_kills.start()  # Start the task to track kills


@tasks.loop(minutes=1)
async def track_kills():
    print("Checking for new kills...")
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found.")
        return

    for player_id in player_ids:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'https://gameinfo-ams.albiononline.com/api/gameinfo/players/{player_id}/kills'
                ) as response:
                    if response.status == 200:
                        kills_data = await response.json()

                        # Sort by most recent kill
                        kills_data.sort(key=lambda kill: kill['TimeStamp'], reverse=True)
                        most_recent_kill = kills_data[0] if kills_data else None

                        if most_recent_kill:
                            kill_time = most_recent_kill['TimeStamp']
                            kill_id = most_recent_kill.get('EventId')

                            # Only send update if the kill is new
                            if player_kills[player_id]['last_kill_time'] is None or kill_time > player_kills[player_id]['last_kill_time']:
                                player_kills[player_id]['last_kill_time'] = kill_time
                                player_kills[player_id]['last_kill_id'] = kill_id

                                player_name = most_recent_kill.get('Killer', {}).get('Name', 'Unknown')
                                target_name = most_recent_kill.get('Victim', {}).get('Name', 'Unknown')
                                location = most_recent_kill.get('Location', 'Unknown')
                                timestamp = kill_time.split('.')[0] + 'Z'
                                killboard_link = f"https://albiononline.com/killboard/kill/{kill_id}"

                                message = (
                                    f"**New Kill Alert!**\n\n"
                                    f"**Player:** {player_name}\n"
                                    f"**Target:** {target_name}\n"
                                    f"**Location:** {location}\n"
                                    f"**Timestamp:** {timestamp}\n\n"
                                    f"Check out the kill details: [View Kill]({killboard_link})"
                                )

                                await channel.send(message)
                                print(f"New kill detected for {player_id}, sent to channel.")

                    else:
                        print(f"Failed to fetch kills for player {player_id}: {response.status}")

        except Exception as e:
            print(f"Error while fetching data for player {player_id}: {e}")


@bot.command()
async def track(ctx, *new_player_ids):
    if not new_player_ids:
        await ctx.send("Please provide at least one player ID.")
        return

    new_tracked_ids = []

    for player_id in new_player_ids:
        if player_id not in player_ids:
            player_ids.add(player_id)
            new_tracked_ids.append(player_id)
            player_kills[player_id] = {
                'kills': set(),
                'last_kill_time': None,
                'last_kill_id': None
            }

    if new_tracked_ids:
        # Fetch and display the most recent kill for the new players
        response = "Now tracking players:\n"
        for player_id in new_tracked_ids:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                            f'https://gameinfo-ams.albiononline.com/api/gameinfo/players/{player_id}/kills'
                    ) as response_api:
                        if response_api.status == 200:
                            kills_data = await response_api.json()

                            # Sort by most recent
                            kills_data.sort(key=lambda kill: kill['TimeStamp'], reverse=True)
                            most_recent_kill = kills_data[0] if kills_data else None

                            if most_recent_kill:
                                kill_time = most_recent_kill['TimeStamp'].split('.')[0] + 'Z'
                                kill_id = most_recent_kill.get('EventId')
                                killboard_link = f"https://albiononline.com/killboard/kill/{kill_id}"

                                player_kills[player_id]['last_kill_time'] = kill_time
                                player_kills[player_id]['last_kill_id'] = kill_id

                                response += (
                                    f"Player ID: {player_id}\n"
                                    f"Last Kill Time: {kill_time}\n"
                                    f"Killboard Link: {killboard_link}\n\n"
                                )
                            else:
                                response += f"Player ID: {player_id} has no recorded kills yet.\n\n"

            except Exception as e:
                response += f"Error fetching data for player {player_id}: {e}\n\n"

        await ctx.send(response)

    else:
        await ctx.send("No new player IDs added.")


bot.run(BOT_TOKEN)
