# UI design notes

The UI aims to read like a well-set document, not a dashboard. It avoids glow, neon gradients, stacks of cards and emoji.

| Reference | What Kohu takes from it |
|---|---|
| [GOV.UK Design System](https://design-system.service.gov.uk/), see also [GDS on typography and spacing](https://designnotes.blog.gov.uk/2018/02/19/developing-new-typography-and-spacing-for-gov-uk-frontend/) | Black text on white, one link colour (`#1d70b8`), the yellow focus state, inset text (a grey left rule) for the licensed-data notice, warning text (a black circle with "!") for conflicts, summary lists for license terms, plain rules instead of boxes |
| [Gwern.net, sidenotes](https://gwern.net/sidenote), in the Tufte tradition | Citations are small numbered notes in the answer, with the source list underneath, numbered in order of first use |
| Stripe's documentation, as described in third-party analyses such as [this one](https://blakecrosley.com/guides/design/stripe) | A small palette, colour only where it means something (green for a Steward decision), nothing heavier than semibold in the interface, and a detail panel beside the text for the cited source |

Type: answers and quoted passages use a serif (Charter or Georgia), and the interface uses a sans-serif (Inter or the system font). Layout is one 1040 px column that stacks at phone width.
