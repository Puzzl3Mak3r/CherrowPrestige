import discord
import re
import os
import json
from discord import app_commands
from discord.ext import commands
from PIL import Image
from io import BytesIO
import pytesseract
import aiohttp
import matplotlib.pyplot as plt
from datetime import datetime

# Keep alive
from keep_alive import keep_alive

keep_alive()

# File to store prestige data
DATA_FILE = "prestige_data.json"


# Load saved prestige data from file or return empty list
def load_prestige_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


# Save prestige data list to file
def save_prestige_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


# OCR to extract prestige from image, checking for 'cherrowYT'
def extract_prestige(image: Image.Image) -> str | None:
    grayscale = image.convert("L")
    text = pytesseract.image_to_string(grayscale)

    # Check if "cherrowYT" is in the text (case-insensitive)
    if "cherrowyt" not in text.lower():
        return None  # Invalid screenshot

    # Try to find the prestige number
    match = re.search(r"Prestige[:\s]*([0-9,]+)", text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Alternative pattern if heart icon or format varies
    match_alt = re.search(r"cherrowyt\s+(\d{1,3}(?:,\d{3})*)", text.lower())
    if match_alt:
        return match_alt.group(1)

    return "Could not find a prestige value."


# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"🔧 Synced {len(synced)} slash commands.")
    except Exception as e:
        print("Error syncing commands:", e)


# /cpt command - upload screenshot, extract and save prestige
@bot.tree.command(
    name="cpt",
    description=
    "Cherrow Prestige Tracker - Upload a screenshot to extract Prestige.")
@app_commands.describe(
    image="Upload your Cookie Run: Kingdom screenshot here.")
async def cpt(interaction: discord.Interaction, image: discord.Attachment):
    try:
        await interaction.response.defer()
    except discord.errors.NotFound:
        return  # Too late to respond, silently ignore

    if not image.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        await interaction.followup.send(
            "❗ Please upload a PNG, JPG, JPEG, or WEBP image.")
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(image.url) as resp:
            if resp.status == 200:
                img_data = await resp.read()
                img = Image.open(BytesIO(img_data))
                prestige = extract_prestige(img)

                if prestige is None:
                    await interaction.followup.send(
                        "❌ Screenshot does not appear to be from cherrowYT. Please upload a valid screenshot."
                    )
                    return
                elif prestige == "Could not find a prestige value.":
                    await interaction.followup.send(
                        "❌ Could not find a prestige value in the screenshot.")
                    return

                # Load existing data to check for duplicates or lower prestige
                data = load_prestige_data()

                new_prestige_val = int(prestige.replace(",", ""))

                if data:
                    latest_prestige = data[-1]["prestige"]
                    if new_prestige_val < latest_prestige:
                        await interaction.followup.send(
                            "❌ Update screenshot: new prestige is lower than the last logged value."
                        )
                        return
                    elif new_prestige_val == latest_prestige:
                        await interaction.followup.send(
                            "ℹ️ This amount of prestige is already logged.")
                        return

                # Save new prestige
                data.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "prestige": new_prestige_val
                })
                save_prestige_data(data)

                await interaction.followup.send(
                    f"🏅 Prestige: `{prestige}` saved!")
            else:
                await interaction.followup.send(
                    "❌ Failed to download the image.")


# /displayprestige command - display current prestige + graph over time
@bot.tree.command(
    name="displayprestige",
    description=
    "Display current prestige and graph prestige progress over time.")
async def displayP(interaction: discord.Interaction):
    data = load_prestige_data()
    if not data:
        await interaction.response.send_message(
            "No prestige data found. Use /cpt to add data first.")
        return

    # Sort by timestamp
    data.sort(key=lambda x: x["timestamp"])

    # Latest prestige
    current_prestige = data[-1]["prestige"]

    # Prepare graph
    timestamps = [datetime.fromisoformat(d["timestamp"]) for d in data]
    prestiges = [d["prestige"] for d in data]

    plt.figure(figsize=(8, 4))
    plt.plot(timestamps, prestiges, marker="o", linestyle="-")
    plt.title("CherrowYT Prestige Over Time")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Prestige")
    plt.grid(True)
    plt.tight_layout()

    # Save to buffer
    buffer = BytesIO()
    plt.savefig(buffer, format="PNG")
    buffer.seek(0)
    plt.close()

    file = discord.File(fp=buffer, filename="prestige_graph.png")

    # Compose message with info + instructions
    msg = (f"# Current Prestige: `{current_prestige:,}`\n"
           "## To update, use `/cpt` in chat.")

    await interaction.response.send_message(content=msg, file=file)


# Run bot with token from environment variable
token = os.getenv("DISCORD_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN environment variable not set.")
else:
    bot.run(token)
