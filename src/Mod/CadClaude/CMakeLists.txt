# SPDX-License-Identifier: LGPL-2.1-or-later

set(CadClaude_Scripts
    Init.py
    InitGui.py
    cadclaude_worker.py
)

INSTALL(
    FILES
        ${CadClaude_Scripts}
    DESTINATION
        Mod/CadClaude
)

INSTALL(
    DIRECTORY
        elixifree
    DESTINATION
        Mod/CadClaude
)
