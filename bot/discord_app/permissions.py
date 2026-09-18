from __future__ import annotations

import discord

from bot.config.settings import Settings


def can_manage_tracking(interaction: discord.Interaction, settings: Settings) -> bool:
    user = interaction.user
    if user.id in settings.authorized_discord_user_ids:
        return True
    permissions = getattr(user, "guild_permissions", None)
    if permissions is not None and permissions.administrator:
        return True
    roles = getattr(user, "roles", [])
    return any(role.id in settings.authorized_discord_role_ids for role in roles)

