from discord.ext import commands
import discord
import requests
from pymongo import AsyncMongoClient
import csv
import io
import matplotlib.pyplot as plt
from datetime import datetime
import config

class Bitbot(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.client = AsyncMongoClient(config.mongodb)
        self.db = self.client["bitbot"]
        # Register context menu command
        self.bot.tree.add_command(discord.app_commands.ContextMenu(
            name="Download CSV",
            callback=self.download_csv
        ))
        
    async def download_csv(self, interaction: discord.Interaction, message: discord.Message):
        if not interaction.user.guild_permissions.administrator: # Check if user has admin permissions
            await interaction.response.send_message("You need to have administrator permissions to use this command.", ephemeral=True)
            return
        guild_id = str(interaction.guild_id)
        msg_id = message.id
        
        # Check if the message exists in the database
        msg_data = await self.db[guild_id].find_one({"msgid": msg_id})
        if not msg_data:
            await interaction.response.send_message("This message is not a prediction message.", ephemeral=True)
            return
        
        # Create CSV data
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["User ID", "Reaction", "Time"])
        
        up_votes = msg_data["up_votes"]
        down_votes = msg_data["down_votes"]
        
        for user_id, time in up_votes:
            writer.writerow([user_id, "+1", time])
        for user_id, time in down_votes:
            writer.writerow([user_id, "-1", time])
        
        output.seek(0)
        csv_data = output.getvalue()
        
        # Create graph
        plt.figure(figsize=(10, 5))
        
        times_up = [datetime.fromisoformat(time) for _, time in up_votes]
        times_down = [datetime.fromisoformat(time) for _, time in down_votes]
        
        plt.hist([times_up, times_down], bins=20, label=['Up', 'Down'], color=['green', 'red'], alpha=0.7)
        plt.xlabel('Time')
        plt.ylabel('Count')
        plt.title('Prediction Reactions Over Time')
        plt.legend(loc='upper right')
        
        graph_img = io.BytesIO()
        plt.savefig(graph_img, format='png')
        graph_img.seek(0)
        
        # Send CSV data and graph as an ephemeral message
        await interaction.response.send_message(
            content="Here is the CSV data and graph for the prediction reactions:",
            files=[
                discord.File(io.BytesIO(csv_data.encode()), filename="reactions.csv"),
                discord.File(graph_img, filename="reactions.png")
            ],
            ephemeral=True
        )

    @commands.hybrid_command(
        name="predict",
        description="predict a cryptocurrency price"
    )
    async def predict(
        self, 
        ctx: commands.Context,
        currency: str,
        *, 
        attachment: discord.Attachment = None
    ) -> None:
        logo = f"https://cryptologos.cc/logos/thumbs/{currency}.png"
        info = requests.get(f"https://api.coincap.io/v2/assets/{currency}").json().get('data')
        price = float(info.get('priceUsd'))
        formatted_price = f"{price:.4f}"
        embed = discord.Embed(
            description=f"# ${formatted_price}\nWill the price go up or down in next 1 hour?",
            color=discord.Color.yellow()
        )
        embed.set_author(name=info.get("symbol"), icon_url=logo)
        embed.set_thumbnail(url=logo)
        
        if attachment: embed.set_image(url=attachment.url)
        
        msg = await ctx.reply(embed=embed)
        
        await msg.add_reaction("⬆️")
        await msg.add_reaction("⬇️")
        
        # Save message to database
        await self.db[str(ctx.guild.id)].insert_one({
            "msgid": msg.id,
            "up_votes": [],
            "down_votes": []
        })
        
    @commands.hybrid_command(
        name="help",
        description="Shows information about the bot and its commands"
    )
    async def help(self, ctx: commands.Context):
        embed = discord.Embed(
            title="📚 Bitbot Help",
            description="Welcome to Bitbot! A cryptocurrency prediction and tracking bot.",
            color=discord.Color.blue()
        )

        # Commands section
        embed.add_field(
            name="🤖 Commands",
            value=(
                "**`/predict <currency>`**\n"
                "Create a prediction poll for a cryptocurrency price.\n"
                "• `currency`: The cryptocurrency symbol (e.g., bitcoin, ethereum)\n"
                "• Optional: Attach an image for technical analysis\n\n"
                "**`/help`**\n"
                "Display this help message\n"
            ),
            inline=False
        )

        # Context Menu Commands section
        embed.add_field(
            name="📊 Context Menu Features",
            value=(
                "**`Download CSV`** (Admin only)\n"
                "Right-click any prediction message > Apps > Download CSV\n"
                "• Downloads reaction data and displays a graph\n"
                "• Shows who voted and when they voted\n"
            ),
            inline=False
        )

        # Reactions section
        embed.add_field(
            name="⚡ How to Participate",
            value=(
                "1. Find a prediction message\n"
                "2. React with ⬆️ if you think the price will go up\n"
                "3. React with ⬇️ if you think the price will go down\n"
                "4. You can change your prediction by selecting a different reaction\n"
            ),
            inline=False
        )

        embed.set_footer(text="For additional support or questions, contact the server administrators")
        
        await ctx.reply(embed=embed, ephemeral=True)
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        
        guild_id = str(payload.guild_id)
        msg_id = payload.message_id
        user_id = payload.user_id
        time = datetime.utcnow().isoformat()
        
        # Check if the message exists in the database
        msg_data = await self.db[guild_id].find_one({"msgid": msg_id})
        if not msg_data:
            return
        
        if payload.emoji.name == "⬆️":
            await self.db[guild_id].update_one(
                {"msgid": msg_id},
                {"$pull": {"down_votes": {"$in": [user_id]}}, "$addToSet": {"up_votes": [user_id, time]}}
            )
        elif payload.emoji.name == "⬇️":
            await self.db[guild_id].update_one(
                {"msgid": msg_id},
                {"$pull": {"up_votes": {"$in": [user_id]}}, "$addToSet": {"down_votes": [user_id, time]}}
            )
        
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        
        guild_id = str(payload.guild_id)
        msg_id = payload.message_id
        user_id = payload.user_id
        
        # Check if the message exists in the database
        msg_data = await self.db[guild_id].find_one({"msgid": msg_id})
        if not msg_data:
            return
        
        if payload.emoji.name == "⬆️":
            await self.db[guild_id].update_one(
                {"msgid": msg_id},
                {"$pull": {"up_votes": {"$in": [user_id]}}}
            )
        elif payload.emoji.name == "⬇️":
            await self.db[guild_id].update_one(
                {"msgid": msg_id},
                {"$pull": {"down_votes": {"$in": [user_id]}}}
            )
        
    @commands.command()
    async def sync(self, ctx):
        self.bot.tree.copy_global_to(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)
        
        
async def setup(bot):
    await bot.add_cog(Bitbot(bot))
