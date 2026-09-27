# Terminal and fetch

## kitty palette

| Slot | Name | Winter | Polar night |
|---|---|---|---|
| bg / fg | background / foreground | #f7f9fb / #1d242d | #151b22 / #dfe6ed |
| cursor | amber block, no blink | #9a5e0f | #f6bd55 |
| selection | bg / fg | #fbdea3 / #1d242d | #5a4520 / #f3f6f9 |
| 0 / 8 | black / bright black | #1d242d / #5f6b79 | #2a3440 / #8392a3 |
| 1 / 9 | red | #b3261e / #c43a2c | #ef8a84 / #ffa39c |
| 2 / 10 | green (lichen) | #1d7350 / #237f5b | #7fcf9b / #9ee6b6 |
| 3 / 11 | yellow (amber) | #84500d / #a35f0c | #f2b857 / #ffd07f |
| 4 / 12 | blue (ice) | #1f5f9e / #2e6eb0 | #80b0e8 / #a2c8f2 |
| 5 / 13 | magenta (fireweed) | #8a3d86 / #9c4b98 | #d49ccf / #e8b8e3 |
| 6 / 14 | cyan (glacier) | #136c76 / #1a7c87 | #72cfd3 / #9be3e6 |
| 7 / 15 | white / bright white | #66727f / #3e4a58 | #c3ccd6 / #f3f6f9 |

Colours 1–15 hold 4.5:1 on the background in both themes. Colour 0 in Polar night is intentionally near the background (it is the "black"). In Winter, 7 and 15 are dark slates so programs that print "white" or "bright white" stay readable on the light background.

## arctic-fetch

The fox is drawn with Unicode block elements so it matches the mark. `A` marks an amber eye cell (`color3` █); every other cell is the foreground colour.

```
rest
  ▗█▖         ▗█▖
  ███▙       ▟███   ▗▄
  ████▙▄▄▄▄▄▟████   ██▌
  ███A███████A███   ▐█▌
   ▜███████████▛    ▟█▘
 ▄   ▜███████▛     ▟██
 ▜▙    ▜███▛    ▗▟██▛
  ▀██▄▄▄▄▄▄▄▄▄▄███▀▘

blink
  ▗█▖         ▗█▖
  ███▙       ▟███   ▗▄
  ████▙▄▄▄▄▄▟████   ██▌
  ███████████████   ▐█▌
   ▜███████████▛    ▟█▘
 ▄   ▜███████▛     ▟██
 ▜▙    ▜███▛    ▗▟██▛
  ▀██▄▄▄▄▄▄▄▄▄▄███▀▘

ear
               ▗█▖
  ▀██▙       ▟███   ▗▄
  ████▙▄▄▄▄▄▟████   ██▌
  ███A███████A███   ▐█▌
   ▜███████████▛    ▟█▘
 ▄   ▜███████▛     ▟██
 ▜▙    ▜███▛    ▗▟██▛
  ▀██▄▄▄▄▄▄▄▄▄▄███▀▘

tail
  ▗█▖         ▗█▖
  ███▙       ▟███
  ████▙▄▄▄▄▄▟████   ▗█▖
  ███A███████A███   ▐██▌
   ▜███████████▛    ▐█▌
 ▄   ▜███████▛     ▟██▘
 ▜▙    ▜███▛    ▗▟██▛
  ▀██▄▄▄▄▄▄▄▄▄▄███▀▘
```

Sequence (ms): rest 900 · blink 140 · rest 500 · ear 180 · rest 260 · ear 140 · rest 420 · tail 220 · rest 200 · tail 180 — played twice, then it stays on rest. Info column (2 spaces after the fox): `user@host` (user `color3` bold, host bold), a `color8` rule, then `os base kernel wm shell term theme uptime` with keys in `color6`, then two rows of swatches (colours 0–7, 8–15).

Implementation sketch (zsh, interactive shells only):

```sh
arctic-fetch() {
  [[ -o interactive ]] || return
  local frames=(rest blink rest ear rest ear rest tail rest tail) ms=(0.9 0.14 0.5 0.18 0.26 0.14 0.42 0.22 0.2 0.18)
  tput civis; arctic-fetch-draw rest            # draws fox + info once
  if [[ -z $ARCTIC_REDUCE_MOTION ]]; then
    for loop in 1 2; do for i in {1..10}; do
      printf '\e[%dA' 8; arctic-fetch-fox ${frames[i]}; sleep ${ms[i]}   # redraw only the 8 fox rows
    done; done
    printf '\e[%dA' 8; arctic-fetch-fox rest
  fi
  tput cnorm
}
```
