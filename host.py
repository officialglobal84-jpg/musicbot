import discord
from discord.ext import commands
import yt_dlp
import asyncio
import random
import time
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix=["!", "."],
    intents=intents,
    help_command=None
)
music_queue = []

current_song = None
current_thumbnail = None
current_requester = None

song_start = 0
song_duration = 0

current_volume = 0.5
player_message = None

loop_song = False
loop_queue = False

# ---------------- FFMPEG ----------------

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn"
}

# ---------------- YTDLP ----------------

ytdl = yt_dlp.YoutubeDL({
    "format": "bestaudio/best",
    "quiet": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0"
})

# ================= STATUS ROTATION =================

async def status_rotation():

    await bot.wait_until_ready()

    statuses = [
        discord.Activity(type=discord.ActivityType.playing, name="Developed by Beni"),
        discord.Activity(type=discord.ActivityType.watching, name="Playing Music"),
        discord.Activity(type=discord.ActivityType.playing, name="Global On Top"),
        discord.Activity(type=discord.ActivityType.watching, name="Global Cheats")
    ]

    while not bot.is_closed():

        for status in statuses:
            await bot.change_presence(activity=status)
            await asyncio.sleep(5)

# ================= PROGRESS BAR =================

def progress_bar():

    if song_duration == 0:
        return "LIVE"

    elapsed = max(0, int(time.time() - song_start))

    if elapsed > song_duration:
        elapsed = song_duration

    progress = int((elapsed / song_duration) * 15)

    bar = "▰" * progress + "▱" * (15-progress)

    def fmt(t):
        m,s = divmod(t,60)
        return f"{m}:{s:02}"

    return f"{fmt(elapsed)} {bar} {fmt(song_duration)}"

# ================= PLAYER UPDATE =================

async def update_player():

    while True:

        if player_message and current_song:

            embed = discord.Embed(
                title="🎶 Now Playing",
                description=f"**{current_song}**",
                color=0xff0000
            )

            embed.add_field(name="Progress", value=progress_bar(), inline=False)
            embed.add_field(name="Requester", value=current_requester.mention)
            embed.add_field(name="Volume", value=f"{int(current_volume*100)}%")

            loop_mode = "Off"

            if loop_song:
                loop_mode = "Song 🔂"

            elif loop_queue:
                loop_mode = "Queue 🔁"

            embed.add_field(name="Loop", value=loop_mode)

            embed.set_thumbnail(url=current_thumbnail)

            try:
                await player_message.edit(embed=embed)
            except:
                pass

        await asyncio.sleep(1)

# ================= BUTTONS =================

class MusicButtons(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=600)

    def check(self, interaction):

        if interaction.user.voice is None:
            return False

        vc = interaction.guild.voice_client

        if vc is None:
            return False

        return interaction.user.voice.channel == vc.channel

    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.gray)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not self.check(interaction):
            return await interaction.response.send_message("Join VC first", ephemeral=True)

        vc = interaction.guild.voice_client

        if vc.is_playing():
            vc.pause()

        await interaction.response.send_message("Paused", ephemeral=True)

    @discord.ui.button(emoji="▶", style=discord.ButtonStyle.green)
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not self.check(interaction):
            return await interaction.response.send_message("Join VC first", ephemeral=True)

        interaction.guild.voice_client.resume()

        await interaction.response.send_message("Resumed", ephemeral=True)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.blurple)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not self.check(interaction):
            return await interaction.response.send_message("Join VC first", ephemeral=True)

        interaction.guild.voice_client.stop()

        await interaction.response.send_message("Skipped", ephemeral=True)

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not self.check(interaction):
            return await interaction.response.send_message("Join VC first", ephemeral=True)

        music_queue.clear()
        interaction.guild.voice_client.stop()

        await interaction.response.send_message("Stopped", ephemeral=True)

# ================= PLAY NEXT =================

async def play_next(ctx):

    global current_song,current_thumbnail,current_requester
    global song_start,song_duration,player_message

    if not music_queue:
        return

    vc = ctx.voice_client

    if not vc:
        return

    url,title,duration,thumbnail,requester = music_queue.pop(0)

    if loop_queue:
        music_queue.append((url,title,duration,thumbnail,requester))

    current_song = title
    current_thumbnail = thumbnail
    current_requester = requester

    song_duration = duration
    song_start = time.time()

    data = ytdl.extract_info(url,download=False)
    stream = data["url"]

    source = discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(stream, **FFMPEG_OPTIONS),
        volume=current_volume
    )

    def after_playing(error):

        if loop_song:
            music_queue.insert(0,(url,title,duration,thumbnail,requester))

        if not bot.is_closed():
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

    vc.play(source,after=after_playing)

    embed = discord.Embed(
        title="🎶 Now Playing",
        description=f"**{title}**",
        color=0xff0000
    )

    embed.add_field(name="Progress",value=progress_bar(),inline=False)
    embed.add_field(name="Requester",value=requester.mention)

    embed.set_thumbnail(url=thumbnail)

    global player_message
    player_message = await ctx.send(embed=embed,view=MusicButtons())

# ================= PLAY =================

@bot.command(aliases=["p"])
async def play(ctx, *, query):

    if not ctx.voice_client:

        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
            await ctx.send(f"✅ Joined **{ctx.author.voice.channel.name}**")
        else:
            return await ctx.send("❌ Join VC first")

    await ctx.send(f"🔍 Searching **{query}**...")

    info = ytdl.extract_info(f"ytsearch1:{query}", download=False)

    data = info["entries"][0]

    url = data["webpage_url"]
    title = data["title"]
    duration = data.get("duration",0)
    thumbnail = data["thumbnail"]

    music_queue.append((url,title,duration,thumbnail,ctx.author))

    if not ctx.voice_client.is_playing():
        await play_next(ctx)

    else:
        await ctx.send(f"➕ Added **{title}**")

# ================= COMMANDS =================

@bot.command()
async def join(ctx):

    if not ctx.author.voice:
        return await ctx.send("❌ Join a voice channel first")

    if ctx.voice_client:
        return await ctx.send("⚠️ Already connected")

    await ctx.author.voice.channel.connect()

    await ctx.send(f"✅ Joined **{ctx.author.voice.channel.name}**")

@bot.command()
async def leave(ctx):

    if not ctx.voice_client:
        return await ctx.send("❌ Not connected")

    channel = ctx.voice_client.channel.name

    await ctx.voice_client.disconnect()

    await ctx.send(f"👋 Left **{channel}**")

@bot.command()
async def queue(ctx):

    if not music_queue:
        return await ctx.send("Queue empty")

    embed = discord.Embed(title="🎶 Queue",color=0xff0000)

    for i,song in enumerate(music_queue[:10]):

        embed.add_field(
            name=f"{i+1}. {song[1]}",
            value=f"Requested by {song[4].mention}",
            inline=False
        )

    embed.set_footer(text=f"{len(music_queue)} songs")

    await ctx.send(embed=embed)

@bot.command()
async def shuffle(ctx):

    if not music_queue:
        return await ctx.send("Queue empty")

    random.shuffle(music_queue)

    await ctx.send("🔀 Queue shuffled")

@bot.command()
async def clear(ctx):

    music_queue.clear()

    await ctx.send("🗑 Queue cleared")

@bot.command()
async def remove(ctx,number:int):

    if 0 < number <= len(music_queue):

        removed = music_queue.pop(number-1)

        await ctx.send(f"Removed **{removed[1]}**")

@bot.command()
async def volume(ctx,volume:int):

    global current_volume

    if 1 <= volume <= 200:

        current_volume = volume/100

        if ctx.voice_client and ctx.voice_client.source:
            ctx.voice_client.source.volume = current_volume

        await ctx.send(f"🔊 Volume {volume}%")

@bot.command()
async def ping(ctx):

    await ctx.send(f"🏓 {round(bot.latency*1000)}ms")

# ================= HELP =================

@bot.command()
async def help(ctx):

    embed = discord.Embed(
        title="🎵 Beni Music System",
        description="High Power Music Bot",
        color=0xff0000
    )

    embed.add_field(
        name="🎶 Music",
        value="""
`!play <song>`
`!skip`
`!stop`
`!queue`
""",
        inline=False
    )

    embed.add_field(
        name="📜 Queue",
        value="""
`!shuffle`
`!remove <number>`
`!clear`
""",
        inline=False
    )

    embed.add_field(
        name="⚙ Controls",
        value="""
`!volume`
`!join`
`!leave`
`!ping`
""",
        inline=False
    )

    embed.set_footer(text="Developed by Beni")

    await ctx.send(embed=embed)

# ================= ERROR HANDLER =================

@bot.event
async def on_command_error(ctx,error):

    if isinstance(error,commands.CommandNotFound):
        return

    await ctx.send(f"Error: {error}")

# ================= READY =================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

    await asyncio.sleep(2)

    bot.loop.create_task(status_rotation())
    bot.loop.create_task(update_player())

bot.run(TOKEN)