# GradPath design language

The Univet university reference guides the campus hero, navy navigation, gold actions and serif headings. GradPath uses its own campus artwork and the shared styles in `gradpath/static/app/app.css`.

## Locked identity

- Use cream `#f6f4ee` behind white cards, navy `#073352` for navigation and gold `#ffcc49` for primary actions. Set body text in `#142b40`.
- Set headings and the wordmark in Georgia. Keep the existing platform sans stack for form labels, explanations and financial figures.
- Rhythm: existing 4/8/12/16/24/32/48/64px scale. Radius: 6/10/16px. Use one outline icon family already in the app. Do not add decorative motion; respect reduced motion.
- Signature: each editable financial amount is paired with its clear annual interpretation. Published figures sit next to a prominent verification link and a visible source year.
- Voice: plain dollars and time periods, with direct qualifiers for estimates and source dates. No unexplained score, prestige label or promise of affordability.

## Usage lock

Reuse these tokens and semantic controls throughout the planner. A new field must have a visible label, optional/required status, hint, inline error and keyboard focus. Keep exactly one primary action on each step. Source data must remain distinct from user-entered estimates. Maintain text contrast of at least 4.5:1 and non-text controls at least 3:1; the existing palette was selected for AA contrast. Responsive layouts collapse to one column before fields become cramped.
