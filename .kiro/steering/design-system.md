# Design System

## Identity: Code Autopsy / Clinical X-Ray
The app looks like a specialized engineering diagnostic instrument for dissecting code, not a generic AI SaaS dashboard. Clinical, precise, high-contrast, restrained, and slightly unsettling through engineering metaphors rather than Halloween decoration.

## Colors
| Purpose | Color |
|---|---|
| Primary matte obsidian | `#09090B` |
| Elevated matte surface | `#111113` |
| Bone-white primary text | `#F4F4F5` |
| Muted zinc secondary text | `#A1A1AA` |
| Structural hairline borders | `#27272A` |
| Diagnostic crimson | `#DC2626` |
| Secondary diagnostic red | `#EF4444` |
| Verified / mastered emerald | `#10B981` |

- **Crimson/red** marks real diagnostic states: unaudited modules, haunted code, spec drift, structural risks, failed verification.
- **Emerald** marks real verified states: passing verification, mastered modules, verified structural nodes.
- Color communicates system state. It is never decoration.

## Typography
- Crisp, readable sans-serif for UI text.
- Monospace for code, identifiers, paths, hashes, diagnostic output, and technical metadata.
- Build hierarchy with weight, spacing, and scale, not decorative effects.

## Prohibited
Purple AI gradients, neon glows, bloom, glowing blobs, cartoon Halloween art, pumpkins, cartoon ghosts, generic AI-dashboard layouts, heavily rounded cards, cluttered SaaS boilerplate, and any decoration with no functional meaning.

## Functional Costume Contest
Every spooky or forensic visual must map to a real engineering state.
- A shroud/static layer = an unaudited AI-generated module or architectural blind spot.
- A bone-white skeletal graph = the actual AST or call structure.
- Crimson markings = a real diagnostic or unaudited condition.
- Clearing the shroud = successful Socratic verification.
- Emerald = verified or mastered.

Spooky styling must improve comprehension and function.

## Mode Toggle
The UI must support an instant toggle between `Autopsy Mode` and `Lab Mode`. It maps to Study Mode OFF and ON respectively, as defined in `product.md`, and must change behavior, not only appearance.
