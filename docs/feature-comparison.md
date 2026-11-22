# FoodBridge vs. Feeding India, OLIO, Too Good To Go

None of these existing platforms is a competitor in the same lane as
FoodBridge — each solves a related but different problem. FoodBridge's pitch
is **a combination none of them offer**: B2B surplus-to-NGO logistics, with a
live safety clock, a smart first-look match, and an auditable handover code,
purpose-built for the hotel/NGO relationship rather than consumer donation or
discounted retail.

| Capability | **FoodBridge** | Feeding India (Zomato) | OLIO | Too Good To Go |
|---|---|---|---|---|
| Primary users | Hotels/restaurants ↔ verified NGOs and individuals | Donors ↔ NGO network (centrally coordinated) | Neighbours ↔ neighbours (P2P) | Businesses ↔ paying consumers |
| Who receives the food | Verified NGOs, plus admin-verified individuals (small quantities) | NGO partners (vetted by Feeding India) | Any individual | Any paying consumer |
| Money changes hands | No — pure donation | No | No | Yes — discounted "surprise bags" |
| Live safety countdown tied to travel time | **Yes — Safe-Until Clock compares food safety window to estimated NGO travel time** | No published equivalent | No | Pickup window shown, but not matched to realistic travel time |
| Automatic best-match + first-look window | **Yes — Smart Match ranks by distance/capacity/reliability, 10-min first look** | Routed by Feeding India's own team/process | No — first-come, chat-based | No — first-come within the app |
| Verifiable, single-use handover code | **Yes — random-salt derived 6-digit code (never stored), single use, expires with the food, lockout after 5 tries, full attempt log** | Not published | No | Order confirmation, not a collection-verification code |
| NGO reliability score, visible publicly | **Yes** | Not published to donors | User ratings (general, not reliability-specific) | Business ratings only |
| Needs board (NGOs broadcast what they need) | **Yes** | No | No | No |
| Printable per-donor impact certificate with transparent CO2 formula | **Yes, formula shown on the certificate** | General impact reporting (aggregate, not per-donor on demand) | No | General impact stats (app-wide, not per-business) |
| Role-based verification gate before any activity | **Yes — Admin approves every Hotel/NGO before posting/requesting** | Managed internally by Feeding India | No formal verification | Business-side verification; consumer side open |
| Works fully offline / no required third-party key | **Yes — haversine fallback, bundled Bootstrap** | N/A (not open source) | N/A | N/A |

**Takeaway:** Feeding India centrally coordinates donations through its own
operations team; OLIO is peer-to-peer with no verification or logistics
automation; Too Good To Go is a paid marketplace for near-expiry retail, not
restaurant surplus donation. FoodBridge is the one designed specifically for
the hotel-to-verified-NGO handoff, with safety timing, smart matching, and an
auditable handover baked into the core flow — a combination the others don't
assemble together.
