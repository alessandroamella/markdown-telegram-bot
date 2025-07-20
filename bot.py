import logging
import os

import telegramify_markdown
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegramify_markdown import customize

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
WHITELIST = (
    list(map(int, os.getenv("WHITELIST", "").split(",")))
    if os.getenv("WHITELIST")
    else []
)

# Customize telegramify-markdown settings
config = customize.get_runtime_config()
config.markdown_symbol.head_level_1 = "📌"
config.markdown_symbol.head_level_2 = ""
config.markdown_symbol.head_level_3 = ""
config.markdown_symbol.head_level_4 = ""
config.markdown_symbol.link = "🔗"
config.cite_expandable = True


class MarkdownBot:
    def __init__(self, token: str, whitelist: list):
        self.token = token
        self.whitelist = whitelist
        self.application = Application.builder().token(token).build()

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_markdown)
        )

    async def start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command"""
        user_id = update.effective_user.id

        if user_id not in self.whitelist:
            logger.info(f"Unauthorized user {user_id} tried to start the bot")
            return

        welcome_message = """
🤖 **Markdown Formatter Bot**

Send me any markdown text and I'll format it for Telegram!

Supported features:
• Headings (# ## ### etc.)
• **Bold** and *italic* text
• Links [text](url)
• Code blocks and `inline code`
• Lists and tables
• Block quotes
• Strikethrough ~~text~~
• Spoilers ||text||
• And much more!

Just send me your markdown text and I'll convert it to proper Telegram format.
        """

        formatted = telegramify_markdown.markdownify(welcome_message.strip())
        await update.message.reply_text(formatted, parse_mode="MarkdownV2")

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /help command"""
        user_id = update.effective_user.id

        if user_id not in self.whitelist:
            return

        help_text = """
📖 **How to use this bot:**

1\\. Send me any markdown text
2\\. I'll convert it to Telegram's MarkdownV2 format
3\\. The formatted message will be sent back to you

**Example:**
```
# My Title
This is **bold** and this is *italic*
- Item 1
- Item 2
```

**Supported markdown:**
• Headers \\(\\# \\#\\# \\#\\#\\#\\)
• **Bold** and *italic*
• Links \\[text\\]\\(url\\)
• Code blocks and \\`inline code\\`
• Lists \\(ordered and unordered\\)
• Tables
• Block quotes \\(\\>\\)
• Strikethrough \\~\\~text\\~\\~
• Spoilers \\|\\|text\\|\\|
• LaTeX math expressions
        """

        await update.message.reply_text(help_text, parse_mode="MarkdownV2")

    async def handle_markdown(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle markdown text messages"""
        user_id = update.effective_user.id

        # Check if user is whitelisted
        if user_id not in self.whitelist:
            logger.info(f"Unauthorized user {user_id} tried to use the bot")
            return

        # Get the message text
        markdown_text = update.message.text

        try:
            # Use telegramify instead of markdownify for long text handling
            # This automatically splits long messages and handles formatting
            message_chunks = telegramify_markdown.telegramify(
                markdown_text,
                max_word_count=2000,  # Adjust chunk size as needed
                split_long_words=True,
                normalize_whitespace=False,
            )

            # Send each chunk as a separate message
            for i, chunk in enumerate(message_chunks):
                if chunk.text.strip():  # Only send non-empty chunks
                    # Add chunk indicator for multi-part messages
                    if len(message_chunks) > 1:
                        chunk_header = f"📄 *Part {i+1}/{len(message_chunks)}*\n\n"
                        final_text = chunk_header + chunk.text
                    else:
                        final_text = chunk.text

                    await update.message.reply_text(final_text, parse_mode="MarkdownV2")

                # Handle any files/images that might be generated
                if hasattr(chunk, "files") and chunk.files:
                    for file_info in chunk.files:
                        if file_info.get("type") == "image":
                            # Send as photo if it's an image
                            await update.message.reply_photo(
                                photo=file_info["file"],
                                caption=file_info.get("caption", ""),
                            )
                        else:
                            # Send as document for other file types
                            await update.message.reply_document(
                                document=file_info["file"],
                                caption=file_info.get("caption", ""),
                            )

            logger.info(
                f"Successfully formatted and sent {len(message_chunks)} message chunks for user {user_id}"
            )

        except Exception as e:
            logger.error(f"Error formatting message: {e}")

            # Fallback to simple markdownify for shorter messages
            try:
                logger.info("Attempting fallback to markdownify...")
                formatted_text = telegramify_markdown.markdownify(
                    markdown_text, max_line_length=None, normalize_whitespace=False
                )

                # Check if message is too long for Telegram (4096 chars limit)
                if len(formatted_text) > 4000:
                    # Split manually if still too long
                    chunks = [
                        formatted_text[i : i + 4000]
                        for i in range(0, len(formatted_text), 4000)
                    ]
                    for i, chunk in enumerate(chunks):
                        chunk_header = (
                            f"📄 *Part {i+1}/{len(chunks)}*\n\n"
                            if len(chunks) > 1
                            else ""
                        )
                        await update.message.reply_text(
                            chunk_header + chunk, parse_mode="MarkdownV2"
                        )
                else:
                    await update.message.reply_text(
                        formatted_text, parse_mode="MarkdownV2"
                    )

                logger.info(f"Fallback successful for user {user_id}")

            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                # Send error message in a safe format
                error_text = str(e).replace(".", "\\.")
                error_msg = (
                    f"❌ Sorry, I couldn't format your message\\. Error: `{error_text}`"
                )
                await update.message.reply_text(error_msg, parse_mode="MarkdownV2")

    async def error_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle errors"""
        logger.error(f"Update {update} caused error {context.error}")

    def run(self):
        """Start the bot"""
        # Add error handler
        self.application.add_error_handler(self.error_handler)

        logger.info("Starting Markdown Formatter Bot...")
        logger.info(f"Whitelisted users: {self.whitelist}")

        # Start the bot
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    # Validate configuration
    if not BOT_TOKEN:
        print("❌ Please set your BOT_TOKEN in the .env file!")
        print("Get your bot token from @BotFather on Telegram")
        print("Create a .env file with: BOT_TOKEN=your_token_here")
        return

    if not WHITELIST:
        print("❌ Please add user IDs to the WHITELIST in the .env file!")
        print("You can get your user ID by messaging @userinfobot on Telegram")
        print("Add to .env file: WHITELIST=123456789,987654321")
        return

    # Create and run bot
    bot = MarkdownBot(BOT_TOKEN, WHITELIST)
    bot.run()


if __name__ == "__main__":
    main()
