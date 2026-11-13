# GradPath design language

**Design read:** A calm worksheet for decisions with real financial consequences. **Direction:** technical/utilitarian, with a warm accent so a long calculation still feels approachable. This is a product interface, built with the existing semantic HTML and CSS tokens in `gradpath/static/app/app.css`; no component framework is introduced.

## Locked identity

- Surface `#ffffff`, background `#fbf8f5`, primary text `#1f1a17`, secondary `#5b4f47`, borders `#e5dbd2` and `#b9aca1`. Orange `#c2410c` is reserved for the primary action and active navigation; `#9a3412` for linked text and hover. Blue `#1d4ed8` identifies keyboard focus.
- Type: the existing platform sans stack, body 1rem / 1.55, bold section headings, tabular or aligned numeric facts. The platform font is intentional here: the familiar shape helps long financial forms stay legible on student devices. Keep the existing `--text-*` scale.
- Rhythm: existing 4/8/12/16/24/32/48/64px scale. Radius: 6/10/16px. Use one outline icon family already in the app. Do not add decorative motion; respect reduced motion.
- Signature: each editable financial amount is paired with its clear annual interpretation. Published figures sit next to a prominent verification link and a visible source year.
- Voice: plain dollars and time periods, with direct qualifiers for estimates and source dates. No unexplained score, prestige label or promise of affordability.

## Usage lock

Reuse these tokens and semantic controls throughout the planner. A new field must have a visible label, optional/required status, hint, inline error and keyboard focus. Keep exactly one primary action on each step. Source data must remain distinct from user-entered estimates. Maintain text contrast of at least 4.5:1 and non-text controls at least 3:1; the existing palette was selected for AA contrast. Responsive layouts collapse to one column before fields become cramped.
