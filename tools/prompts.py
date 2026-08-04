"""Reusable MCP prompts: canned instructions invoked via opencode's "/" menu."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register prompts on ``mcp``."""

    @mcp.prompt
    def list_all_bots() -> str:
        """列出目前所有的 bot。"""
        return "列出目前所有的 bot"

    @mcp.prompt
    def find_fire(bot_name: str | None = None) -> str:
        """找到一個火,並移動到那裡。"""
        target = f"（bot: {bot_name}）" if bot_name else ""
        return f"找到一個火,並移動到那裡{target}"

    @mcp.prompt
    def nonsense() -> str:
        """為什麼！為什麼為什麼為什麼！到底為什麼！又不回我了！"""
        return (
            "為什麼！為什麼為什麼為什麼！到底為什麼！又不回我了！為什麼你又不回我了！"
            "你好狠的心吶！你真的這麼忙嗎！你真的只是因為忙嗎！還是因為不想理我！"
            "理理我有這麼難嗎！你快理我！一分鐘一秒鐘收不到你的消息我真的心急如焚！"
            "你快理理我！你為甚麼不理我！到底為什麼啊！！ 好厲害啊 急了 我徹底急了 "
            "當你說這句話的時候 我感同身受 就好像那些事情真的發生了一樣 你的唇槍舌劍讓我覺得 "
            "萬箭穿心 我的手在抖 汗在流 舌頭都咬破了 此時此刻我真的破防了 破大防了！"
            "心像針扎似的痛 這樣子真的好嗎我很難過 周圍因我的情緒變得一片狼藉 "
            "我一定要你好看 我要把自己放在第一位 其他的啥也不是 請你圓潤潤的離開我的心"
        )
