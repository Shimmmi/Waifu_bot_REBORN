# Merc ops board art

Static keys: `ops_bias_{reward_bias}.webp` under this folder.

| art_key | Bias motif |
|---------|------------|
| ops_bias_merc_coins | pay chest / coins |
| ops_bias_merc_dust | crystal dust |
| ops_bias_merc_exp | training manuals |
| ops_bias_contracts | sealed contracts |
| ops_bias_tickets | arena tickets |
| ops_bias_mixed | mixed spoils |

Admin: `POST /admin/ops-art/generate?art_key=ops_bias_merc_coins`

Prompt template (code: `ops_art_generation.OPS_ART_PROMPT_TEMPLATE`):

> Dark fantasy watercolor tavern operations briefing poster, no text… Subject motif: {bias hint}. Moody tavern lighting…
