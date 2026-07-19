"""DeepSeek API provider.

DeepSeek's API is OpenAI-compatible and supports tool calls, so this reuses
the exact message/tool conversion and chat logic as the DigitalOcean
(nvidia) provider — only the client endpoint and key differ. Chosen over
the DO-hosted DeepSeek R1 because R1 is a reasoning model with weaker
function calling, and every Flinch role is tool-driven; deepseek-v4-flash
is the cheap, tool-calling V4 model (see config.DEEPSEEK_MODEL).
"""
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

# Reuse the OpenAI-shape conversion + chat loop verbatim.
from agent.providers.nvidia import chat, _convert_tools, _convert_messages  # noqa: F401


def create_client():
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
