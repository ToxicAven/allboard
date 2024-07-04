import sqlite3
import discord
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()


if not os.getenv("STARBOARD_WEBHOOK"):
    raise Exception("STARBOARD_WEBHOOK not found in .env file")

if not os.getenv("DISCORD_TOKEN"):
    raise Exception("DISCORD_TOKEN not found in .env file")

if not os.getenv("THRESHOLD"):
    print("WARN: THRESHOLD not found in .env file, defaulting to 5")
    THRESHOLD = 5
else:
    THRESHOLD = int(os.getenv("THRESHOLD"))


client = discord.Client(intents=discord.Intents(reactions=True, message_content=True))
webhookClient = discord.SyncWebhook.from_url(os.getenv("STARBOARD_WEBHOOK"))


def prepareDB():
    if not os.path.exists("data.db"):
        open("data.db", "w").close()

    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY,
        emotedMessage INTEGER NOT NULL,
        trackedEmoji STRING NOT NULL,
        boardMessage INTEGER NOT NULL,
        maxReactions INTEGER NOT NULL
    )"""
    )
    conn.commit()
    conn.close()


async def handleStarboard(message: discord.Message, reaction: discord.Reaction):
    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute(
        "SELECT * FROM messages WHERE emotedMessage = ? AND trackedEmoji = ?",
        (message.id, str(reaction.emoji)),
    )
    row = c.fetchone()

    # don't do anything if the message has already been posted to the starboard
    # and the reaction count is less than the max
    if row and row[4] >= reaction.count:
        return

    embed = discord.Embed(
        author=discord.EmbedAuthor(
            name=message.author.display_name,
            url=message.jump_url,
            icon_url=message.author.display_avatar.url,
        ),
        description=message.content,
        footer=discord.EmbedFooter(
            text=f'{datetime.now().strftime("%d/%m/%y %H:%M:%S")}'
        ),
        color=discord.Color.random(),
    )

    imgSet = False
    if message.attachments:
        for a in message.attachments:
            if a.content_type.startswith("image"):
                embed.set_image(url=a.url)
                imgSet = True
                break

    if not imgSet and message.embeds:
        for e in message.embeds:
            if e.type == "gifv":
                embed.set_image(url=e.url)
                break
            elif e.type == "image":
                embed.set_image(url=e.url)
                break

    if row:
        starboard_message: discord.SyncWebhookMessage = webhookClient.fetch_message(
            row[3]
        )
        starboard_message.edit(embed=embed)
        c.execute(
            "UPDATE messages SET maxReactions = ? WHERE id = ?",
            (max(row[4], reaction.count), row[0]),
        )
        conn.commit()
        conn.close()

    else:
        starboard_message = webhookClient.send(
            wait=True,
            content=f"**{reaction.count} {reaction.emoji}** | {message.jump_url}",
            embed=embed,
        )

        c.execute(
            "INSERT INTO messages (emotedMessage, trackedEmoji, boardMessage, maxReactions) VALUES (?, ?, ?, ?)",
            (message.id, str(reaction.emoji), starboard_message.id, reaction.count),
        )
        conn.commit()
        conn.close()


@client.event
async def on_ready():
    print(f"{client.user} has connected to Discord!")

    prepareDB()

    print(
        "Invite Link: https://discord.com/oauth2/authorize?client_id={0}&scope=bot&permissions={1}".format(
            client.user.id, discord.Permissions(read_messages=True).value
        )
    )


@client.event
async def on_raw_reaction_add(event: discord.RawReactionActionEvent):
    channel = await client.fetch_channel(event.channel_id)
    if channel.type == discord.ChannelType.private:
        return

    message = await channel.fetch_message(event.message_id)

    for reaction in message.reactions:
        hasSelfReacted = await reaction.users().get(id=message.author.id) is not None
        if hasSelfReacted:
            reaction.count -= 1
        if reaction.count >= THRESHOLD:
            await handleStarboard(message, reaction)


client.run(os.getenv("DISCORD_TOKEN"))
