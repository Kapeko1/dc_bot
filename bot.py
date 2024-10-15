import discord
from discord.ext import commands, tasks
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import io


BOT_TOKEN = ''
CHANNEL_ID = 1286326334188028087

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

player_kills = {}
player_ids = set()


# Function to create an inventory image with a grid layout
async def create_inventory_image(full_inventory):
    # Define the size of each item icon and the number of columns
    icon_size = 64
    columns = 10  # Number of icons per row
    padding = 5  # Padding between icons

    # Calculate the number of rows needed based on the number of items
    total_items = len(full_inventory)
    rows = (total_items // columns) + (1 if total_items % columns != 0 else 0)

    # Create an image with enough space for all items in a grid layout
    img_width = columns * (icon_size + padding) - padding
    img_height = rows * (icon_size + padding) - padding
    img = Image.new('RGB', (img_width, img_height), color=(73, 109, 137))

    # Load the bold font from the same folder as the bot
    font = ImageFont.truetype("ARIALBD.TTF", 18)  # Ensure the font size is correct for your needs

    x_offset = 0
    y_offset = 0

    async with aiohttp.ClientSession() as session:
        for index, (item_slot, item_info) in enumerate(full_inventory.items()):
            if item_info:
                # Fetch the item icon
                item_icon_url = f"https://render.albiononline.com/v1/item/{item_info['Type']}.png?size=64"
                async with session.get(item_icon_url) as icon_response:
                    if icon_response.status == 200:
                        icon_data = await icon_response.read()
                        icon_image = Image.open(io.BytesIO(icon_data)).resize((icon_size, icon_size))

                        # Paste the icon into the grid at the current position
                        img.paste(icon_image, (x_offset, y_offset))

                        # Check if there is a quantity and overlay it on the icon
                        item_quantity = item_info.get('Count', 1)  # Default to 1 if no quantity is specified
                        if item_quantity > 1:
                            draw = ImageDraw.Draw(img)

                            # Set the position to slightly right (5px to the right of the bottom-right corner)
                            text_position = (
                            x_offset + icon_size - 21, y_offset + icon_size - 18)  # Adjusted for new position

                            # Draw the quantity text (bold and white)
                            draw.text(text_position, str(item_quantity), font=font, fill=(255, 255, 255))

                        # Update x_offset for the next icon
                        x_offset += icon_size + padding

                        # Move to the next row if the current row is filled
                        if (index + 1) % columns == 0:
                            x_offset = 0
                            y_offset += icon_size + padding

    # Save the image to an in-memory buffer
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return buffer


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    track_kills.start()


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

                        # Log if there is kill data fetched from the API
                        if kills_data:
                            print(f"Kills data fetched for player {player_id}")
                        else:
                            print(f"No kills data for player {player_id}")

                        # Sort by most recent kills
                        kills_data.sort(key=lambda kill: kill['TimeStamp'], reverse=True)

                        # Initialize player kill history if not present
                        if player_id not in player_kills:
                            player_kills[player_id] = {
                                'last_kill_time': None,
                                'last_kill_id': None,
                                'processed_kills': set()  # New: Track processed kills
                            }

                        new_kills = [kill for kill in kills_data if kill['EventId'] not in player_kills[player_id]['processed_kills']]

                        for kill in new_kills:
                            kill_time = kill['TimeStamp']
                            kill_id = kill.get('EventId')

                            # Log the kill time and ID for debugging
                            print(f"New kill time: {kill_time}, kill ID: {kill_id}")

                            player_name = kill.get('Killer', {}).get('Name', 'Unknown')
                            target_name = kill.get('Victim', {}).get('Name', 'Unknown')
                            location = kill.get('Location', 'Unknown')
                            timestamp = kill_time.split('.')[0] + 'Z'
                            killboard_link = f"https://albiononline.com/killboard/kill/{kill_id}"

                            victim_equipment = kill.get('Victim', {}).get('Equipment', {})
                            victim_inventory = kill.get('Victim', {}).get('Inventory', {})

                            full_inventory = {**victim_equipment, **{f'Inventory_Item_{i}': item for i, item in enumerate(victim_inventory) if item}}

                            message = (
                                f"**New Kill Alert!**\n\n"
                                f"**Player:** {player_name}\n"
                                f"**Target:** {target_name}\n"
                                f"**Location:** {location}\n"
                                f"**Timestamp:** {timestamp}\n\n"
                                f"Check out the kill details: [View Kill]({killboard_link})"
                            )
                            await channel.send(message)

                            # Generate inventory image and send it
                            if full_inventory:
                                buffer = await create_inventory_image(full_inventory)
                                file = discord.File(buffer, filename="inventory.png")
                                await channel.send(file=file)

                            print(f"Kill alert sent for {player_id}.")

                            # Mark this kill as processed
                            player_kills[player_id]['processed_kills'].add(kill_id)

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
        response = "Now tracking players:\n"
        for player_id in new_tracked_ids:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                            f'https://gameinfo-ams.albiononline.com/api/gameinfo/players/{player_id}/kills'
                    ) as response_api:
                        if response_api.status == 200:
                            kills_data = await response_api.json()

                            # Sort by most recent kill
                            kills_data.sort(key=lambda kill: kill['TimeStamp'], reverse=True)
                            most_recent_kill = kills_data[0] if kills_data else None

                            if most_recent_kill:
                                kill_time = most_recent_kill['TimeStamp'].split('.')[0] + 'Z'
                                kill_id = most_recent_kill.get('EventId')
                                killboard_link = f"https://albiononline.com/killboard/kill/{kill_id}"

                                player_kills[player_id]['last_kill_time'] = kill_time
                                player_kills[player_id]['last_kill_id'] = kill_id

                                # Extract victim equipment and inventory
                                victim_equipment = most_recent_kill.get('Victim', {}).get('Equipment', {})
                                victim_inventory = most_recent_kill.get('Victim', {}).get('Inventory', {})

                                # Combine equipment and inventory
                                full_inventory = {**victim_equipment, **{f'Inventory_Item_{i}': item for i, item in enumerate(victim_inventory) if item}}

                                response += (
                                    f"Player ID: {player_id}\n"
                                    f"Last Kill Time: {kill_time}\n"
                                    f"Killboard Link: {killboard_link}\n\n"
                                )

                                # Generate inventory image and send it
                                if full_inventory:
                                    buffer = await create_inventory_image(full_inventory)
                                    file = discord.File(buffer, filename="inventory.png")
                                    await ctx.send(file=file)

                            else:
                                response += f"Player ID: {player_id} has no recorded kills yet.\n\n"

            except Exception as e:
                response += f"Error fetching data for player {player_id}: {e}\n\n"

        await ctx.send(response)

    else:
        await ctx.send("No new player IDs added.")


bot.run(BOT_TOKEN)
