# Memoria di Claude Code per questo progetto

Copia dei file di memoria di Claude Code (decisioni, preferenze, stato del lavoro), portata qui per
spostare il lavoro dal Codespace a un PC. Non è usata dal programma.

## Ripristino sul PC

Claude Code legge la memoria da `~/.claude/projects/<cartella del progetto>/memory/`, dove il nome della
cartella è il percorso del progetto con `/`, `\` e `:` sostituiti da `-`. Per esempio:

| Progetto in | Cartella della memoria |
|---|---|
| `/home/mario/cvap-turnistica` | `~/.claude/projects/-home-mario-cvap-turnistica/memory/` |
| `C:\Users\Mario\cvap-turnistica` | `%USERPROFILE%\.claude\projects\C--Users-Mario-cvap-turnistica\memory\` |

Il modo più sicuro:

1. avvia `claude` una volta nella cartella del progetto ed esci;
2. guarda quale cartella è comparsa in `~/.claude/projects/`;
3. crea lì dentro la cartella `memory` e copiaci i file `.md` di questa cartella (tranne questo LEGGIMI).

Linux/Mac, dalla cartella del progetto:

```bash
D=~/.claude/projects/$(pwd | sed 's#[/:\\]#-#g')/memory
mkdir -p "$D" && cp memoria-claude/*.md "$D" && rm "$D/LEGGIMI.md"
```

Windows (PowerShell), dalla cartella del progetto:

```powershell
$D = "$env:USERPROFILE\.claude\projects\" + ((Get-Location).Path -replace '[\\/:]', '-') + "\memory"
New-Item -ItemType Directory -Force $D | Out-Null
Copy-Item memoria-claude\*.md $D -Exclude LEGGIMI.md
```

Il plugin `ecc` va installato anche sul PC (`/plugin marketplace add affaan-m/everything-claude-code`,
poi `/plugin install ecc@ecc`).

Per ripartire: `claude` nella cartella del progetto, poi "Riprendiamo il piano rotazioni dalla fase 4".
