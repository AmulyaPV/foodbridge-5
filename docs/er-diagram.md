# FoodBridge — ER Diagram

```mermaid
erDiagram
    USER ||--o| HOTELPROFILE : "has (if role=hotel)"
    USER ||--o| NGOPROFILE : "has (if role=ngo)"
    USER ||--o| INDIVIDUALPROFILE : "has (if role=individual)"
    USER ||--o{ LISTINGREPORT : "files"
    USER ||--o{ NOTIFICATION : receives
    USER ||--o{ ACTIVITYLOG : "acts as"
    USER ||--o| USER : "verified_by (self)"

    HOTELPROFILE ||--o{ FOODLISTING : posts
    FOODLISTING ||--|{ FOODITEM : contains
    FOODLISTING ||--o{ LISTINGPHOTO : has
    FOODLISTING ||--o{ LISTINGMATCH : "first-look matches"
    FOODLISTING ||--o{ PICKUPREQUEST : "receives"
    FOODLISTING ||--o{ LISTINGREPORT : "is reported by"

    PICKUPREQUEST ||--o| HANDOVERCODE : "secured by (after confirmation)"
    HANDOVERCODE ||--o{ HANDOVERATTEMPT : "logs every try"
    USER ||--o{ HANDOVERATTEMPT : "types code"

    NGOPROFILE ||--o{ PICKUPREQUEST : "makes (as NGO)"
    INDIVIDUALPROFILE ||--o{ PICKUPREQUEST : "makes (as individual)"
    NGOPROFILE ||--o{ LISTINGMATCH : "matched to"
    NGOPROFILE ||--o{ NGONEED : posts

    USER {
        bigint id PK
        string username
        string email
        string password
        string role "hotel / ngo / individual / admin"
        string verification_status "pending / approved / rejected / suspended"
        string verification_note
        datetime verified_at
        bigint verified_by_id FK
    }

    HOTELPROFILE {
        bigint id PK
        bigint user_id FK
        string name
        string contact_person
        string phone
        text address
        float latitude
        float longitude
        string fssai_number UK
        image photo
    }

    INDIVIDUALPROFILE {
        bigint id PK
        bigint user_id FK
        string name "full name"
        string phone
        text address
        float latitude
        float longitude
        int household_size
        file supporting_document
    }

    LISTINGREPORT {
        bigint id PK
        bigint listing_id FK
        bigint reporter_id FK
        string reason "unsafe / misleading / inappropriate / other"
        string details
        string status "open / actioned / dismissed"
        bigint resolved_by_id FK
        datetime resolved_at
    }

    NGOPROFILE {
        bigint id PK
        bigint user_id FK
        string name
        string contact_person
        string phone
        text address
        float latitude
        float longitude
        string registration_number UK
        int daily_capacity
        string service_area
        file certificate
    }

    FOODLISTING {
        bigint id PK
        bigint hotel_id FK
        string title "food name (falls back to item names)"
        text pickup_location "falls back to hotel address"
        string contact_phone "falls back to hotel phone"
        text storage_notes "storage and handling"
        int total_servings
        int servings_available
        datetime pickup_window_start
        datetime pickup_window_end
        datetime safe_until
        string status "posted/fulfilled/expired/cancelled/removed"
        string cancel_reason
        string removal_reason
        datetime created_at
    }

    FOODITEM {
        bigint id PK
        bigint listing_id FK
        string name
        string category "veg/non_veg/vegan"
        decimal quantity
        string unit "servings/kg/packets"
        string cooking_time_note
        string allergens_note
    }

    LISTINGPHOTO {
        bigint id PK
        bigint listing_id FK
        image image
    }

    LISTINGMATCH {
        bigint id PK
        bigint listing_id FK
        bigint ngo_id FK
        smallint rank
        float distance_km
    }

    PICKUPREQUEST {
        bigint id PK
        bigint listing_id FK
        bigint ngo_id FK "null when an individual asks"
        bigint individual_id FK "null when an NGO asks"
        int amount
        string status "requested/confirmed/rejected/on_the_way/collected/cancelled/expired"
        string reject_reason
        string cancel_reason
        smallint eta_minutes
        datetime on_the_way_at
        datetime requested_at
        datetime approved_at "when it was confirmed"
        datetime collected_at
        bool was_approved "was ever confirmed"
    }

    HANDOVERCODE {
        bigint id PK
        bigint pickup_request_id FK,UK "one code per pickup"
        string salt "random 128-bit; the 6 digits are derived, never stored"
        string status "active / used / locked"
        datetime issued_at
        datetime expires_at "= listing.safe_until"
        smallint failed_attempts "cumulative, max 5"
        smallint regenerations "max 2"
        datetime locked_at
        datetime used_at
        bigint used_by_id FK
    }

    HANDOVERATTEMPT {
        bigint id PK
        bigint handover_id FK
        bigint actor_id FK
        string outcome "success / wrong / expired / blocked"
        string ip_address
        datetime created_at
    }

    NGONEED {
        bigint id PK
        bigint ngo_id FK
        int servings_needed
        datetime needed_by
        string notes
        string status "open/closed"
    }

    NOTIFICATION {
        bigint id PK
        bigint user_id FK
        string kind
        string message
        string link
        bool is_read
        datetime created_at
    }

    ACTIVITYLOG {
        bigint id PK
        bigint actor_id FK
        string action
        string message
        string target_type
        bigint target_id
        datetime created_at
    }
```

## Notes

- `USER` is a single table with a `role` discriminator (hotel / ngo / admin)
  rather than separate Django auth models, so one login system serves all
  three roles.
- `HOTELPROFILE` / `NGOPROFILE` are each a strict one-to-one extension of
  `USER` — only populated for the matching role.
- Indexes are on `FOODLISTING(status, safe_until)` (for expiry sweeps and the
  NGO browse page), `PICKUPREQUEST(status)`, `NOTIFICATION(user, is_read)`,
  and `(latitude, longitude)` on both profile tables.
- A partial unique constraint on `PICKUPREQUEST(listing, ngo)` — scoped to the
  active statuses (`requested/confirmed/on_the_way`) — stops an NGO from
  holding two simultaneous open requests on the same listing, while still
  letting history accumulate (a rejected, then a fresh request, is fine).
- `HANDOVERCODE` is split out of `PICKUPREQUEST` so the security state (salt,
  counters, lock, expiry) lives in one place and the request table stays about
  the request. `HANDOVERATTEMPT` is append-only and never stores the digits typed.
