"""Blueprints. Para criar um novo módulo: crie routes/<modulo>.py com `bp` e adicione-o aqui."""
from app.routes import (auth, backup, campaigns, characters, dashboard, items, media, messages, notes, npcs, players,
                        quests, sessions, xp)

all_blueprints = [
    auth.bp, dashboard.bp, campaigns.bp, players.bp, characters.bp, xp.bp, notes.bp,
    sessions.bp, npcs.bp, quests.bp, items.bp, backup.bp, messages.bp, media.bp,
]
