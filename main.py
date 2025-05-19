import discord
import re
import os
import json
from discord import app_commands
from discord.ext import commands
from io import BytesIO
import aiohttp
import matplotlib.pyplot as plt
from datetime import datetime

# Keep alive for web service on Render
from keep_alive import keep_alive

keep_alive()

DATA_FILE = "prestige_data.json"

def load_prestige_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_prestige_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

async def extract_prestige(image_bytes: bytes) -> str | None:
    api_key = os.getenv("OCR_SPACE_API_KEY")
    if not api_key:
        raise ValueError("OCR_SPACE_API_KEY environment variable not set")

    url = "https://api.ocr.space/parse/image"
    headers = {"apikey": api_key}
    data = {"language": "eng", "isOverlayRequired": False}

    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field("file", image_bytes, filename="image.jpg", content_type="image/jpeg")
        for key, value in data.items():
            form.add_field(key, str(value))

        async with session.post(url, data=form, headers=headers) as resp:
            result = await resp.json()
            try:
                parsed_text = result["ParsedResults"][0]["ParsedText"]
            except (KeyError, IndexError):
                return "❌ OCR failed to extract text."

    if "cherrowyt" not in parsed_text.lower():
        return None

    match = re.search(r"Prestige[:\s]*([0-9,]+)", parsed_text, re.IGNORECASE)
    if match:
        return match.group(1)

    match_alt = re.search(r"cherrowyt\s+(\d{1,3}(?:,\d{3})*)", parsed_text.lower())
    if match_alt:
        return match_alt.group(1)

    return "Could not find a prestige value."

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

@bot.tree.command(
    name="cpt",
    description="Cherrow Prestige Tracker - Upload a screenshot to extract Prestige.")
@app_commands.describe(image="Upload your Cookie Run: Kingdom screenshot here.")
async def cpt(interaction: discord.Interaction, image: discord.Attachment):
    print(f"Interaction received at: {interaction.created_at}")
    try:
        await interaction.response.defer()
    except discord.errors.NotFound:
        print("⚠️ Interaction expired before defer!")
        return

    if not image.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        await interaction.followup.send("❗ Please upload a PNG, JPG, JPEG, or WEBP image.")
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(image.url) as resp:
            if resp.status == 200:
                img_data = await resp.read()
                prestige = await extract_prestige(img_data)

                if prestige is None:
                    await interaction.followup.send("❌ Screenshot does not appear to be from cherrowYT.")
                    return
                elif prestige == "Could not find a prestige value.":
                    await interaction.followup.send("❌ Could not find a prestige value in the screenshot.")
                    return

                data = load_prestige_data()
                new_prestige_val = int(prestige.replace(",", ""))

                if data:
                    latest_prestige = data[-1]["prestige"]
                    if new_prestige_val < latest_prestige:
                        await interaction.followup.send("❌ Update rejected: prestige is lower than last recorded.")
                        return
                    elif new_prestige_val == latest_prestige:
                        await interaction.followup.send("ℹ️ This prestige is already logged.")
                        return

                data.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "prestige": new_prestige_val
                })
                save_prestige_data(data)

                await interaction.followup.send(f"🏅 Prestige: `{prestige}` saved!")
            else:
                await interaction.followup.send("❌ Failed to download the image.")

@bot.tree.command(
    name="displayprestige",
    description="Display current prestige and graph prestige progress over time.")
async def displayP(interaction: discord.Interaction):
    data = load_prestige_data()
    if not data:
        await interaction.response.send_message("No prestige data found. Use /cpt to add data first.")
        return

    data.sort(key=lambda x: x["timestamp"])
    current_prestige = data[-1]["prestige"]

    timestamps = [datetime.fromisoformat(d["timestamp"]) for d in data]
    prestiges = [d["prestige"] for d in data]

    plt.figure(figsize=(8, 4))
    plt.plot(timestamps, prestiges, marker="o", linestyle="-")
    plt.title("CherrowYT Prestige Over Time")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Prestige")
    plt.grid(True)
    plt.tight_layout()

    buffer = BytesIO()
    plt.savefig(buffer, format="PNG")
    buffer.seek(0)
    plt.close()

    file = discord.File(fp=buffer, filename="prestige_graph.png")
    msg = f"# Current Prestige: `{current_prestige:,}`\n## To update, use `/cpt`."

    await interaction.response.send_message(content=msg, file=file)

# Run bot
token = os.getenv("DISCORD_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN environment variable not set.")
else:
    bot.run(token)
