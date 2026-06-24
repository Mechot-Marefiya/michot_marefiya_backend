# React API Guide
# Platform: Michot Marefiya
# Backend: Django REST Framework
# Last updated: 2026-06-21

This document is the React-facing API reference built from `schema.yaml` as the primary source.

Scope rules used here:

- included: public, regular-user, company-staff, front-desk, and individual-owner endpoints needed by the React app
- excluded: Flutter-only guidance, Django-admin-only workflows, and admin-only moderation/monitoring endpoints
- role mapping in this guide:
  - `regular_user` maps to backend role `user`
  - `company_staff` maps to backend company-side access, including `company` and `front_desk`
  - `individual_owner` maps to backend role `individual_owner`

Listing state rules:

- new cars, hotels, hotel rooms, property rentals, property sales, guest houses, and guest-house rooms are created with `is_active=true` and `is_verified=false`
- verification is admin-controlled trust metadata; do not treat unverified as hidden
- public listing/search endpoints return active listings
- owner/managed inventory endpoints must show the caller's own listings whether active, inactive, verified, or unverified

## Section 1: Authentication (all roles)

### Obtain JWT Token
Workflow reference: `REACT_WORKFLOW.md` Section 2
Method: `POST`
URL: `/api/v1/auth/token/`
Auth: no
Roles: all

Request body:
- `phone`: string - required - phone-based login identifier
- `password`: string - required - user password

Query params:
- none

Success response (HTTP 200):
- `refresh`: string - refresh token
- `access`: string - access token
- `role`: string|null - backend role code
- `company`: object|null - login profile summary with `id`, `name`
- `individual_owner`: object|null - login profile summary with `id`, `name`
- `workspace`: object|null - workspace info with `id`, `name`, `workspace_type`

Error responses:
- `401`: invalid credentials - shape is generic object from schema

React notes:
- this is the stable login contract; do not build React around email login
- route after login from `role` and `workspace`, not by guesswork

### Refresh JWT Token
Workflow reference: `REACT_WORKFLOW.md` Section 2
Method: `POST`
URL: `/api/v1/auth/token/refresh/`
Auth: no
Roles: all

Request body:
- `refresh`: string - required - refresh token

Query params:
- none

Success response (HTTP 200):
- `access`: string - new access token

Error responses:
- `401`: invalid or expired refresh token - generic auth failure shape

React notes:
- keep this in the API client layer
- if refresh fails, clear session state and redirect to login

### Request OTP
Workflow reference: `REACT_WORKFLOW.md` Section 2
Method: `POST`
URL: `/api/v1/auth/otp/request/`
Auth: no
Roles: all

Request body:
- `phone`: string - required - target phone number
- `purpose`: enum - optional - defaults to `login`

Query params:
- none

Success response (HTTP 200):
- `success`: boolean - request accepted
- `challenge_id`: uuid - OTP challenge id
- `challenge_token`: uuid - companion challenge token
- `purpose`: string - OTP purpose
- `expires_at`: datetime - challenge expiry
- `cooldown_seconds`: integer - resend cooldown
- `phone`: string - normalized phone used for the challenge

Error responses:
- `400`: invalid phone or blocked request - generic object shape

React notes:
- `challenge_token` and `cooldown_seconds` are additive contract fields React must support
- use this same flow for login verification and other phone-verification checkpoints

### Verify OTP
Workflow reference: `REACT_WORKFLOW.md` Section 2
Method: `POST`
URL: `/api/v1/auth/otp/verify/`
Auth: no
Roles: all

Request body:
- `challenge_id`: uuid - optional in schema, but typically sent - issued by OTP request
- `challenge_token`: uuid - optional in schema, but typically sent - companion token
- `code`: string - required - OTP code
- `purpose`: enum - optional - defaults to `login`

Query params:
- none

Success response (HTTP 200):
- `success`: boolean - verification result
- `purpose`: string - resolved verification purpose
- `user`: object|null - user payload when verification resolves a user flow
- `access`: string - JWT access token when auth tokens are issued
- `refresh`: string - JWT refresh token when auth tokens are issued
- `role`: string|null - backend role when auth tokens are issued
- `guest_verification_token`: string - reusable guest verification token when a guest flow is verified
- `guest_history_transfer`: object - optional guest-linking metadata

Error responses:
- `400`: invalid, expired, or mismatched OTP - generic object shape

React notes:
- treat auth-token issuance and guest verification as separate possible outcomes
- do not assume every OTP verify response contains tokens

## Section 2: User Profile (all roles)

### Read Current User
Workflow reference: `REACT_WORKFLOW.md` Section 2
Method: `GET`
URL: `/api/v1/auth/me/`
Auth: no
Roles: all

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- `id`: uuid - user id
- `email`: string - email address
- `first_name`: string
- `last_name`: string
- `phone`: string|null
- `phone_verified`: boolean
- `phone_verified_at`: datetime|null
- `last_known_lat`: decimal|null
- `last_known_lng`: decimal|null
- `location_updated_at`: datetime|null
- `location_permission_granted`: boolean
- `is_active`: boolean
- `role`: object|null - role payload
- `workspace`: object|null - workspace info with `id`, `name`, `workspace_type`

Error responses:
- `401`: missing or invalid token - generic auth failure shape

React notes:
- this is the safest post-login source for routing and capability checks
- render `workspace.workspace_type` for company-side shell selection

### Read / Update My Profile
Workflow reference: `REACT_WORKFLOW.md` Section 2
Method: `GET` / `PATCH`
URL: `/api/v1/account/users/me/`
Auth: no
Roles: all

Request body:
- `email`: string - optional on patch - email
- `first_name`: string - optional on patch
- `last_name`: string - optional on patch
- `phone`: string|null - optional on patch
- `phone_verified_at`: datetime|null - optional on patch
- `last_known_lat`: decimal|null - optional on patch
- `last_known_lng`: decimal|null - optional on patch
- `location_updated_at`: datetime|null - optional on patch
- `location_permission_granted`: boolean - optional on patch
- `is_active`: boolean - optional on patch

Query params:
- none

Success response (HTTP 200):
- same shape as `UserResponse`

Error responses:
- `400`: validation errors - usually `{ "field_name": ["error"] }`
- `401`: unauthenticated

React notes:
- if the backend rejects phone changes, surface the message exactly
- do not expose fields like `phone_verified_at` as editable UI unless the product explicitly wants them

### Store User Location
Workflow reference: `REACT_WORKFLOW.md` Section 6
Method: `POST`
URL: `/api/v1/account/location/`
Auth: no
Roles: all

Request body:
- `lat`: decimal - required - current latitude
- `lng`: decimal - required - current longitude
- `permission_granted`: boolean - required - whether the browser granted location access

Query params:
- none

Success response (HTTP 200):
- `lat`: decimal - persisted latitude
- `lng`: decimal - persisted longitude
- `location_permission_granted`: boolean
- `location_updated_at`: datetime

Error responses:
- `400`: invalid coordinates or request body
- `401`: unauthenticated

React notes:
- call this only after an intentional location-permission moment
- keep browsing usable even if this never runs

### Convert Guest Bookings
Workflow reference: `REACT_WORKFLOW.md` Section 2
Method: `POST`
URL: `/api/v1/account/users/me/convert-guest-bookings/`
Auth: yes (Bearer)
Roles: regular_user

Request body:
- `otp_challenge_id`: uuid - optional - when guest linkage needs explicit OTP proof
- `otp_code`: string - optional - OTP code for linkage

Query params:
- none

Success response (HTTP 200):
- `success`: boolean
- `phone`: string
- `verified_via`: string
- `linked_counts`: object
- `already_linked_counts`: object
- `linked_total`: integer
- `already_linked_total`: integer

Error responses:
- `400`: OTP mismatch or no linkable guest history
- `401`: unauthenticated

React notes:
- useful after signup or first authenticated login if the same phone was used as a guest

## Section 3: Regular User - Discovery

### Feed Listings
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/feed/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `listing_type`: enum - optional - `all`, `hotel`, `guesthouse`, `event_space`, `car_rental`, `car_sales`, `property_rental`, `property_sales`
- `page`: integer - optional

Success response (HTTP 200):
- `count`: integer
- `total_pages`: integer
- `current_page`: integer
- `page_size`: integer
- `next`: string|null
- `previous`: string|null
- `results`: array of `ProximityListing`

Per result:
- `id`: uuid
- `listing_type`: string
- `title`: string
- `description`: string
- `latitude`: decimal|null
- `longitude`: decimal|null
- `formatted_address`: string|null
- `place_id`: string|null
- `price_preview`: decimal|null
- `currency`: string
- `thumbnail_url`: string|null
- `rating`: number|null
- `is_verified`: boolean
- `distance_km`: number

Error responses:
- `400`: invalid query params - generic object shape

React notes:
- React must support the newer listing type filters from the changelog
- `distance_km` may be meaningful only when proximity mode is active

### Search Listings
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/search/`
Auth: no
Roles: all

Request body:
- none

Query params:
- search and location filters are supported by this endpoint
- use listing-type and map-context filters the backend exposes

Success response (HTTP 200):
- paginated results using `ListingSearchResult`

Per result:
- `id`: uuid
- `listing_type`: string
- `title`: string
- `description`: string
- `latitude`: decimal|null
- `longitude`: decimal|null
- `formatted_address`: string|null
- `place_id`: string|null
- `price_preview`: decimal|null
- `currency`: string
- `thumbnail_url`: string|null
- `rating`: number|null
- `is_verified`: boolean
- `distance_km`: number|null

Error responses:
- `400`: invalid search filters - generic object shape

React notes:
- this is the unified search surface; do not compute geospatial sorting in the browser

### Search Suggestions
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/search/suggestions/`
Auth: no
Roles: all

Request body:
- none

Query params:
- search term and optional proximity context

Success response (HTTP 200):
- array of `SearchSuggestion`

Per suggestion:
- `id`: uuid
- `listing_type`: string
- `title`: string
- `formatted_address`: string|null
- `thumbnail_url`: string|null
- `rating`: number|null
- `price_preview`: decimal|null
- `distance_km`: number|null
- `latitude`: decimal|null
- `longitude`: decimal|null

Error responses:
- `400`: invalid search input

React notes:
- suggestions are good for autocomplete rows and “jump to listing” interactions

### Nearby Listings
Workflow reference: `REACT_WORKFLOW.md` Section 6
Method: `GET`
URL: `/api/v1/listing/nearby/`
Auth: no
Roles: all

Request body:
- none

Query params:
- location and radius inputs
- optional listing filters

Success response (HTTP 200):
- proximity-oriented result set using `ProximityListing`

Error responses:
- `400`: missing or invalid proximity params

React notes:
- use this for “near me” and radius-based discovery

### Within Bounds Listings
Workflow reference: `REACT_WORKFLOW.md` Section 6
Method: `GET`
URL: `/api/v1/listing/within-bounds/`
Auth: no
Roles: all

Request body:
- none

Query params:
- viewport bounds and optional filters

Success response (HTTP 200):
- `count`, `total_pages`, `current_page`, `page_size`, `next`, `previous`
- `results`: array of `DiscoveryListing`

Per result:
- `id`: uuid
- `listing_type`: string
- `title`: string
- `description`: string
- `latitude`: decimal|null
- `longitude`: decimal|null
- `formatted_address`: string|null
- `place_id`: string|null
- `price_preview`: decimal|null
- `currency`: string
- `thumbnail_url`: string|null
- `rating`: number|null
- `is_verified`: boolean

Error responses:
- `400`: invalid bounds payload

React notes:
- call this when the user pans or zooms the map

### Map Pins
Workflow reference: `REACT_WORKFLOW.md` Section 6
Method: `GET`
URL: `/api/v1/listing/map-pins/`
Auth: no
Roles: all

Request body:
- none

Query params:
- viewport and filter params as supported by the schema

Success response (HTTP 200):
- array of `MapPin`

Per pin:
- `id`: uuid
- `listing_type`: string
- `latitude`: decimal|null
- `longitude`: decimal|null
- `title`: string
- `price_preview`: decimal|null
- `thumbnail_url`: string|null
- `rating`: number|null

Error responses:
- `400`: invalid map query

React notes:
- use this for lightweight pin rendering, not full detail cards

### Room Listings
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/rooms/`
Auth: no
Roles: all

Request body:
- none

Query params:
- pagination and room-related filters supported by schema

Success response (HTTP 200):
- paginated `RoomListingResponse` records

Core response fields:
- `id`, `title`, `description`
- `images`
- `latitude`, `longitude`, `formatted_address`, `place_id`
- `base_price`, `currency`
- `booking_forward_window_days`
- `amenities`, `number_of_guests`, `total_units`, `bed_type`, `room_size_sqm`
- `smoking_allowed`, `children_allowed`, `refundable`
- `available_units`
- `is_verified`, `verified_at`, `verified_by`, `verification_note`
- `conversion`
- `price_quote`

Error responses:
- `400`: invalid filters

React notes:
- `price_quote` is populated only when date context is supplied on detail flows

### Room Listing Detail
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/rooms/{id}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `check_in`: date - optional
- `check_out`: date - optional

Success response (HTTP 200):
- `RoomListingResponse`

Error responses:
- `404`: room not found

React notes:
- if `check_in` and `check_out` are provided, `price_quote` becomes useful for the detail page

### Guest House Profiles
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/guest-houses/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `page`, `page_size`, `search`

Success response (HTTP 200):
- paginated `GuestHouseProfileResponse` records

Core response fields:
- `id`, `title`, `description`, `images`
- `latitude`, `longitude`, `formatted_address`, `place_id`
- `amenities`, `address`, `rating`, `facility`
- `is_favorite`
- `rooms`
- `phone`, `website`, `license`, `logo`
- `is_active`
- `is_verified`, `verified_at`, `verified_by`, `verification_note`

Error responses:
- `400`: invalid filters

React notes:
- this is the correct profile-level detail for guest houses; room-level inventory lives separately

### Guest House Profile Detail
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/guest-houses/{id}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- `GuestHouseProfileResponse`

Error responses:
- `404`: guest house not found

React notes:
- use the embedded `rooms` for previewing guesthouse room choices

### Guest House Room Detail
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/guest-house-rooms/{id}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `check_in`: date - optional
- `check_out`: date - optional

Success response (HTTP 200):
- `GuestHouseRoomResponse`

Core response fields:
- `id`, `title`, `images`
- `latitude`, `longitude`, `formatted_address`, `place_id`
- `base_price`, `currency`
- `booking_forward_window_days`
- `amenities`, `number_of_guests`, `total_units`, `bed_type`, `room_size_sqm`
- `is_verified`, `verified_at`, `verified_by`, `verification_note`
- `conversion`
- `price_quote`

Error responses:
- `404`: room not found

React notes:
- use this endpoint when the UI needs room-specific pricing or availability framing

### Car Listings
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/cars/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `brand`, `car_class`, `condition`, `fuel_type`, `is_active`, `listing_type`, `ordering`, `page`, `page_size`, `search`, `transmission`
- `managed=true`: requires authentication; returns only the caller's owned cars, including inactive and unverified records

Success response (HTTP 200):
- paginated `CarListingResponse` records

Core response fields:
- `id`, `title`, `description`, `images`
- `latitude`, `longitude`, `formatted_address`, `place_id`
- `base_price`, `currency`
- `booking_forward_window_days`
- car attributes such as `brand`, `model`, `year`, `fuel_type`, `transmission`, `condition`, `car_class`, `seats`
- rental/compliance attributes including `rental_mode`, `with_driver_base_price`, `without_driver_base_price`, `pricing_by_rental_mode`, `requires_code_3`, `requires_business_license`, `pre_rental_requirements`
- `business_license_document`: string|null - owner-scoped document URL; public responses may return `null`
- `is_active`: newly registered cars default to `true`
- `is_verified`, `verified_at`, `verified_by`, `verification_note`
- `conversion`

Error responses:
- `400`: invalid car filters

React notes:
- render rental requirements clearly before the user starts a booking
- verification is trust metadata only; active unverified cars remain publicly visible
- use `GET /api/v1/listing/cars/my_listings/` or `GET /api/v1/listing/cars/?managed=true` for owner inventory; both return the caller's owned cars even when inactive or unverified

### Car Listing Detail
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/cars/{id}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- `CarListingResponse`

Error responses:
- `404`: car listing not found

React notes:
- this is the canonical detail endpoint for car-rental product pages

### Car Sale Listings
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/car-sales/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `brand`, `car_class`, `condition`, `fuel_type`, `is_active`, `ordering`, `page`, `page_size`, `search`, `transmission`
- `managed=true`: requires authentication; returns only the caller's company/individual-owner listings, including inactive and unverified records

Success response (HTTP 200):
- paginated `CarSaleListingResponse` records
- with `managed=true`, paginated `CarSaleListingManagedResponse` records

Core response fields:
- `id`, `title`, `description`, `images`
- `latitude`, `longitude`, `formatted_address`, `place_id`
- `base_price`, `currency`
- `brand`, `model`, `year`, `mileage`, `fuel_type`, `transmission`, `condition`, `car_class`, `seats`
- `company`, `individual_owner`
- `reveal_fee`
- `is_active`
- `is_verified`, `verified_at`, `verified_by`, `verification_note`
- `reveal_state`
- `conversion`

Error responses:
- `400`: invalid filters

React notes:
- `reveal_state` is the contact-unlock state machine React should reflect
- public results include active listings regardless of verification status; show verification as trust metadata only
- managed records additionally expose `seller_contact_name`, `seller_phone`, and `seller_email` for owner edit forms; never copy these fields into public cards or detail state

### Car Sale Listing Detail
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/car-sales/{id}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `managed=true`: owner/admin management detail, including stored seller contact

Success response (HTTP 200):
- `CarSaleListingResponse`
- with `managed=true`, `CarSaleListingManagedResponse`

Error responses:
- `404`: car sale listing not found

React notes:
- never derive seller contact from this endpoint; contact reveal is separate
- the exception is an authenticated owner/admin request with `managed=true`, whose `CarSaleListingManagedResponse` contact fields are for provider management only

### Property Listings
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/properties/`
Auth: no
Roles: all

Request body:
- none

Query params:
- pagination and property filters as supported by schema
- `managed=true`: requires authentication; returns only the caller's company/individual-owner listings, including inactive and unverified records

Success response (HTTP 200):
- paginated `PropertyListingResponse` records

Core response fields:
- `id`, `title`, `description`, `images`
- `latitude`, `longitude`, `formatted_address`, `place_id`
- `base_price`, `currency`
- `booking_forward_window_days`
- `address`, `property_type`, `bedrooms`, `bathrooms`, `square_meters`, `is_furnished`
- `conversion`
- `is_verified`, `verified_at`, `verified_by`, `verification_note`

Error responses:
- `400`: invalid filters

React notes:
- this is the main property-rental listing family, not property sales
- owner dashboards should use `managed=true` so inactive/unverified owned records are visible

### Property Listing Detail
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/properties/{id}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- `PropertyListingResponse`

Error responses:
- `404`: property listing not found

React notes:
- show `booking_forward_window_days` in rental booking date UIs when helpful

### Property Sale Listings
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/property-sales/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `is_active`, `is_furnished`, `ordering`, `page`, `page_size`, `property_type`, `search`
- `managed=true`: requires authentication; returns only the caller's company/individual-owner sale listings, including inactive and unverified records, using the managed response with seller contact

Success response (HTTP 200):
- paginated `PropertySaleListingResponse` records for public reads
- paginated `PropertySaleListingManagedResponse` records for `managed=true`

Core response fields:
- same trust and geo fields as other listing responses
- sale-specific fields including property descriptors
- `reveal_fee`
- `reveal_state`
- `is_verified`, `verified_at`, `verified_by`, `verification_note`

Error responses:
- `400`: invalid filters

React notes:
- treat this as a contact-reveal product, not a direct checkout product
- new property-sale listings default to active and unverified

### Property Sale Listing Detail
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/property-sales/{id}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `managed=true`: for owner/admin management detail with seller contact

Success response (HTTP 200):
- `PropertySaleListingResponse` for public reads
- `PropertySaleListingManagedResponse` for `managed=true`

Error responses:
- `404`: property sale listing not found

React notes:
- seller contact is not part of the public detail response

### Event Space Listings
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/event-spaces/`
Auth: no
Roles: all

Request body:
- none

Query params:
- category and capacity filters as supported by schema

Success response (HTTP 200):
- paginated `EventSpaceListingResponse` records

Core response fields:
- `id`, `hotel_id`, `hotel`, `images`, `title`, `description`
- `latitude`, `longitude`, `formatted_address`, `place_id`
- `number_of_guests`, `base_price`, `currency`
- `booking_forward_window_days`
- `amenities`, `total_units`, `space_type`, `floor_area_sqm`
- `conversion`, `price_quote`, `active_terms`, `terms_url`
- `is_active`
- `is_verified`, `verified_at`, `verified_by`, `verification_note`

Error responses:
- `400`: invalid filters

React notes:
- event-space price rendering should rely on backend `price_quote` when date context exists
- `hotel_id` is now the explicit provider scope for multi-hotel event-space management
- `active_terms` can resolve from the event space itself or fall back to hotel/company terms; use `active_terms.scope_type` and `active_terms.scope_id` instead of assuming the source

### Event Space Listing Detail
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/event-spaces/{id}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- date context when supported by the detail contract

Success response (HTTP 200):
- `EventSpaceListingResponse`

Important event-space terms fields:
- `active_terms`: object|null - current effective terms for this event space resolution chain
- `terms_url`: string|null - canonical React fetch route, always `/api/v1/listing/terms/event-space/{event_space_id}/`
- `hotel_id`, `hotel`: selected owning hotel summary
- `is_active`: boolean - public visibility state after verification/activation flow

Error responses:
- `404`: event space not found

React notes:
- use this for event-space booking entry points
- if `active_terms` is null, do not let React claim booking-ready terms are available yet
- TASK-108/TASK-109 flow: fetch `terms_url` or `/api/v1/listing/terms/event-space/{event_space_id}/` before the final booking submit so the acceptance UI is bound to the live resolved terms record

## Section 4: Regular User - Booking

### Hotel Booking Price Preview
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST`
URL: `/api/v1/listing/bookings/price-preview/`
Auth: no
Roles: all

Request body:
- request uses `BookingPreviewRequest`
- includes date range, room selections, and optional guest phone context

Query params:
- `display_currency`: string - optional

Success response (HTTP 200):
- `nights`: integer
- `items`: array of `PricePreviewItem`
- `totals`: object with `items_subtotal`, `platform_fee`, `platform_fee_percentage`, `grand_total`, `currency`
- `conversion`: object|null

Error responses:
- `400`: invalid dates, invalid items, or pricing rules failure

React notes:
- this is the safest place to render totals before booking creation

### Create Hotel Booking
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST`
URL: `/api/v1/listing/bookings/`
Auth: yes (Bearer) / no
Roles: all

Request body:
- request uses `BookingRequest`
- includes `items`, `check_in_date`, `check_out_date`
- guest fields when no authenticated user
- `terms_accepted`: boolean - required
- `terms_version`: string - required
- `payment_currency`: enum - optional
- guest OTP proof fields when guest booking is used

Query params:
- none

Success response (HTTP 201 or 200 depending on implementation path):
- `BookingResponse`

Core response fields:
- `id`, `booking_reference`
- `check_in_date`, `check_out_date`
- `total_price`, `total_room_cost`, `total_addon_cost`, `currency`
- `status`
- `items`
- `conversion`
- `terms_accepted`, `terms_version`, `terms_accepted_at`, `terms_content_snapshot`, `terms_url`
- `guest_*` fields
- `is_resumable`

Error responses:
- `400`: invalid inventory, dates, guest data, or terms acceptance
- `403`: protected ownership or business rule failure

React notes:
- guest checkout now requires the guest OTP checkpoint
- do not move to payment until booking creation succeeds

### View / Cancel Hotel Booking
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET` / `POST`
URL: `/api/v1/listing/bookings/{id}/` and `/api/v1/listing/bookings/{id}/cancel/`
Auth: no
Roles: all

Request body:
- cancel endpoint may require guest cancellation data in guest paths

Query params:
- none

Success response (HTTP 200):
- `BookingResponse`

Error responses:
- `400`: booking not cancelable or invalid guest proof
- `403`: not allowed to view or cancel this booking
- `404`: booking not found

React notes:
- cancellation does not imply refund
- always render returned status, not optimistic local state

### Hotel Booking Lookup
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/bookings/lookup/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `reference`: string - required
- `guest_phone`: string - required

Success response (HTTP 200):
- `BookingResponse`

Error responses:
- `400`: missing required query params, including legacy email-only attempts
- `404`: no booking matches the supplied reference and guest phone pair

React notes:
- send only `reference + guest_phone`; do not send `email`
- Ethiopian phone variants are normalized server-side during lookup

### Guest House Booking Price Preview
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST`
URL: `/api/v1/listing/guesthouse-bookings/price-preview/`
Auth: no
Roles: all

Request body:
- guesthouse booking preview request with dates and room selections

Query params:
- optional display-currency style params if exposed in the contract

Success response (HTTP 200):
- `PricePreviewResponse`

Error responses:
- `400`: invalid dates or inventory request

React notes:
- same rendering rules as hotel preview

### Create / View / Cancel Guest House Booking
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST` / `GET` / `POST`
URL: `/api/v1/listing/guesthouse-bookings/`, `/api/v1/listing/guesthouse-bookings/{id}/`, `/api/v1/listing/guesthouse-bookings/{id}/cancel/`
Auth: yes (Bearer) / no
Roles: all

Request body:
- create uses guesthouse booking request
- includes guest data, terms fields, and guest OTP proof when unauthenticated

Query params:
- none

Success response (HTTP 201 for create, 200 for read/cancel):
- `GuestHouseBookingResponse`

Error responses:
- `400`, `403`, `404` depending on booking validity and ownership

React notes:
- behavior mirrors hotel booking, but with guesthouse inventory

### Guest House Booking Lookup
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/guesthouse-bookings/lookup/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `reference`: string - required
- `guest_phone`: string - required

Success response (HTTP 200):
- `GuestHouseBooking`

Error responses:
- `400`: missing required query params, including legacy email-only attempts
- `404`: no guesthouse booking matches the supplied reference and guest phone pair

React notes:
- same guest recovery contract as hotel booking lookup
- cancelled guesthouse bookings still resolve when the pair matches

### Property Rental Price Preview
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST`
URL: `/api/v1/listing/property-rentals/bookings/price-preview/`
Auth: no
Roles: all

Request body:
- `property_listing`: uuid - required
- `start_date`: date - required
- `end_date`: date - required
- optional guest phone context for first-booking logic

Query params:
- none

Success response (HTTP 200):
- `PricePreviewResponse`

Error responses:
- `400`: invalid date window, unavailable inventory, or invalid property listing

React notes:
- use this before creating a property-rental booking so tax-aware totals can be shown later in payment

### Create / View / Cancel Property Rental Booking
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST` / `GET` / `POST`
URL: `/api/v1/listing/property-rentals/bookings/`, `/api/v1/listing/property-rentals/bookings/{id}/`, `/api/v1/listing/property-rentals/bookings/{id}/cancel/`
Auth: yes (Bearer) / no
Roles: all

Request body:
- `property_listing`: uuid - required
- `start_date`: date - required
- `end_date`: date - required
- `terms_accepted`: boolean - required
- `terms_version`: string - required
- guest fields when unauthenticated
- guest OTP proof when unauthenticated

Query params:
- none

Success response (HTTP 201 for create, 200 for read/cancel):
- `PropertyRentalBookingResponse`

Core response fields:
- `id`, `booking_reference`
- `property_listing`
- `start_date`, `end_date`
- `total_price`, `total_item_cost`, `currency`
- `status`
- `conversion`
- `terms_*`
- `guest_*`
- `snapshot`

Error responses:
- `400`: invalid dates or terms/guest validation
- `403`: not allowed to access this booking
- `404`: booking not found

React notes:
- this booking family is where tax-aware payment breakdown is most important

### Car Rental Price Preview
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST`
URL: `/api/v1/listing/car-rentals/price-preview/`
Auth: no
Roles: all

Request body:
- `CarRental` preview request with listing, date range, units, guest/rental context, and renter-selected mode per item
- each item should send:
  - `car_listing`
  - `units_rent`
  - `selected_rental_mode`: `with_driver` | `without_driver`
- when any selected item uses `without_driver`, preview may also require:
  - `renter_driver_license_number`
  - `renter_code_3_license_number`
  - `renter_business_license_number`

Query params:
- none

Success response (HTTP 200):
- preview object for the rental flow

Error responses:
- `400`: normalized validation contract
```json
{
  "detail": "Price preview could not be created.",
  "errors": {
    "items": [
      {
        "car_listing": ["This car is unavailable for the selected dates."],
        "units_rent": ["Only 1 unit is available."]
      }
    ]
  }
}
```
- use `detail` for summary copy
- use `errors.items[index]` plus top-level field arrays like `end_date` or `renter_driver_license_number` for field messages

React notes:
- use this to display car-rental totals before create
- surface rental requirements from the listing before this step
- compute preview using the renter-selected `selected_rental_mode`, not a single listing-wide price

### Create / View / Cancel Car Rental
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST` / `GET` / `POST`
URL: `/api/v1/listing/car-rentals/`, `/api/v1/listing/car-rentals/{id}/`, `/api/v1/listing/car-rentals/{id}/cancel/`
Auth: yes (Bearer) / no
Roles: all

Request body:
- create uses `CarRentalRequest`
- each `rental_items[]` entry may include `selected_rental_mode`
- guest create requires prior guest OTP request plus `otp_challenge_id` and `otp_code`
- cancel guest path may use `guest_phone`, `guest_verification_token`, `otp_challenge_id`, `otp_code`, `reason`

Query params:
- list accepts `status`, `ordering`, `page`, `page_size`

Success response (HTTP 201 for create, 200 for retrieve/cancel):
- `CarRental`

Core response fields:
- `id`, `booking_reference`
- `start_date`, `end_date`
- `total_price`, `currency`
- `status`
- guest and compliance fields
- `items_details[].selected_rental_mode`
- snapshot and terms fields

Error responses:
- `400`: invalid guest proof or unavailable dates
- `403`: ownership or permission failure
- `404`: rental not found

React notes:
- do not expose confirm, reschedule, or extension actions to regular users unless the product explicitly wants them

### Event Space Price Preview
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST`
URL: `/api/v1/listing/bookings-eventspaces/price-preview/`
Auth: no
Roles: all

Request body:
- event-space preview request with date range and selected spaces

Query params:
- none

Success response (HTTP 200):
- `EventSpacePricePreviewResponse`
- includes standard preview totals plus:
  - `active_terms`: object|null - resolved current terms
  - `terms_url`: string|null - event-space terms fetch route

Error responses:
- `400`: invalid event-space preview request

React notes:
- same preview rendering model as hotel and guesthouse
- use `active_terms` from preview when the booking CTA needs the current accepted terms payload
- if preview returns `active_terms.id`, keep that record and prefer sending it as `terms_id` on booking create

### Create / View Event Space Booking
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST` / `GET`
URL: `/api/v1/listing/bookings-eventspaces/`, `/api/v1/listing/bookings-eventspaces/{id}/`
Auth: yes (Bearer) / no
Roles: all

Request body:
- event-space booking request with items, dates, guest fields, and guest OTP proof when unauthenticated
- `terms_accepted`: boolean - required
- `terms_id`: uuid - optional but preferred when React uses the fetched terms record directly
- `terms_version`: string - required when `terms_id` is not sent
- accepted terms can resolve from event-space terms first, then hotel terms, then company terms

Query params:
- none

Success response (HTTP 201 or 200):
- `EventSpaceBookingResponse`
- includes:
  - `terms_accepted`, `terms_version`, `terms_accepted_at`, `terms_content_snapshot`
  - `accepted_terms`: object|null with `id`, `scope_type`, `scope_id`, `version`, `terms_url`
  - `terms_url`: string|null - current event-space terms route for refresh/review

Error responses:
- `400`, `403`, `404` according to booking validity and ownership

React notes:
- event-space bookings use the same pending-before-payment lifecycle
- do not assume accepted terms always come from the event space itself; read `accepted_terms.scope_type`
- preferred submit contract for TASK-109:
  - fetch current terms from `/api/v1/listing/terms/event-space/{event_space_id}/`
  - store returned `id`, `version`, `scope_type`, and `terms_url`
  - send `terms_id` when that `id` exists
  - send `terms_version` only as a fallback when React does not hold a fetched record id
- after create, use `accepted_terms.scope_type` for receipt/detail labeling instead of assuming the accepted terms belonged to the event space itself

### Event Space Booking Lookup
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/bookings-eventspaces/lookup/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `reference`: string - required
- `guest_phone`: string - required

Success response (HTTP 200):
- `EventSpaceBookingResponse`

Error responses:
- `400`: missing required query params, including legacy email-only attempts
- `404`: no event-space booking matches the supplied reference and guest phone pair

React notes:
- this lookup now follows the same phone-only recovery contract as hotel and guesthouse guest lookup
- do not build any email fallback into the UI

### Initiate Payment
Workflow reference: `REACT_WORKFLOW.md` Section 7
Method: `POST`
URL: `/api/v1/payment/initiate/`
Auth: yes (Bearer) / no
Roles: all

Request body:
- `booking_id`: uuid - required - booking to pay for
- `booking_type`: enum - optional - `booking`, `guesthouse`, `eventspace`, `carrental`, `propertyrental`
- `email`: string - optional
- `first_name`: string - optional
- `last_name`: string - optional
- `amount`: decimal - optional - client expectation only; backend validates against its own calculation
- `currency`: string - optional - requested payment currency

Query params:
- none

Success response (HTTP 200):
- `success`: boolean
- `message`: string
- `checkout_url`: uri|null
- `tx_ref`: string
- `calculated_amount`: string
- `payment_currency`: string
- `exchange_rate`: string
- `original_amount`: string
- `original_currency`: string
- `owner_price`: string|null
- `service_fee`: string|null
- `tax_amount`: string|null
- `tax_rate`: string|null
- `grand_total`: string|null
- `tax_liability_status`: string|null

Error responses:
- `400`: invalid booking reference or payment setup data
- `403`: booking does not belong to current user or is not payable
- `404`: booking not found

React notes:
- redirect to `checkout_url` for hosted checkout by default
- show `grand_total`, `service_fee`, and tax fields before redirect when present

### Verify Payment (Authenticated)
Workflow reference: `REACT_WORKFLOW.md` Section 7
Method: `GET`
URL: `/api/v1/payment/verify/{tx_ref}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- transaction detail payload including:
- `id`, `tx_ref`, `amount`, `currency`, `status`
- `payment_method`, `chapa_transaction_id`
- `receipt_url`
- `owner_price`, `service_fee`
- `tax_amount`, `tax_rate`, `grand_total`, `tax_liability_status`
- `metadata`, `created_at`, `updated_at`
- `chapa_verification`

Error responses:
- `400`, `403`, `404` depending on access and verification state

React notes:
- after returning from Chapa, use backend verification rather than redirect status alone

### Verify Payment (Public / Guest-Safe)
Workflow reference: `REACT_WORKFLOW.md` Section 7
Method: `GET`
URL: `/api/v1/payment/verify-public/{tx_ref}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- public-safe transaction verification payload
- includes transaction status and additive fields such as `receipt_url`, `tax_amount`, `tax_rate`, `grand_total` where available

Error responses:
- `400` or `404` when the transaction cannot be resolved publicly

React notes:
- use this for guest return flows where no user token is available yet

### Cancel Pending Payment
Workflow reference: `REACT_WORKFLOW.md` Section 7
Method: `PUT`
URL: `/api/v1/payment/cancel/{tx_ref}/`
Auth: no
Roles: all

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- `PaymentCancelSuccessResponse` with payment-cancel result

Error responses:
- `400`: payment cannot be cancelled
- `403`: not your transaction
- `404`: unknown `tx_ref`

React notes:
- this cancels pending payment links; it does not refund paid transactions

## Section 5: Regular User - Contact Reveal

### Request Guest OTP for Car-Sale Reveal
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST`
URL: `/api/v1/listing/car-sales/guest-otp/`
Auth: no
Roles: all

Request body:
- `buyer_phone`: string - required

Query params:
- none

Success response (HTTP 201):
- schema response is a generic object

Error responses:
- `400`: invalid phone or request failure

React notes:
- although the schema is generic here, treat this as the guest OTP pre-step for contact reveal

### Request Car-Sale Contact Reveal
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST`
URL: `/api/v1/listing/car-sales/{id}/request-contact/`
Auth: yes (Bearer) / no
Roles: all

Request body:
- `buyer_note`: string - optional
- `buyer_phone`: string - optional but important for guest flow
- `otp_challenge_id`: uuid - optional - guest OTP proof
- `otp_code`: string - optional - guest OTP code
- `guest_verification_token`: string - optional - reusable verified guest token

Query params:
- none

Success response (HTTP 200 / 201):
- schema response is a generic object

Error responses:
- `400`: invalid buyer proof or reveal request
- `403`: not allowed to unlock or duplicate restricted reveal flow

React notes:
- this endpoint starts the reveal state machine and usually leads to payment
- do not send a buyer email; backend derives a Chapa-safe checkout email from the authenticated user or guest phone proof
- do not assume seller contact is included here

### Read Car-Sale Seller Contact
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/car-sales/{id}/contact/`
Auth: yes (Bearer) / no
Roles: all

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- `CarSaleContact` payload with seller contact fields

Error responses:
- `403`: payment not verified or caller not entitled to the contact

React notes:
- only call this after the reveal is actually unlocked

### Request Guest OTP for Property-Sale Reveal
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST`
URL: `/api/v1/listing/property-sales/guest-otp/`
Auth: no
Roles: all

Request body:
- `buyer_phone`: string - required

Query params:
- none

Success response (HTTP 201):
- schema response is a generic object

Error responses:
- `400`: invalid phone or request failure

React notes:
- same role as the car-sale guest OTP endpoint

### Request Property-Sale Contact Reveal
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `POST`
URL: `/api/v1/listing/property-sales/{id}/request-contact/`
Auth: yes (Bearer) / no
Roles: all

Request body:
- same `ContactRevealRequestRequest` shape as car sales:
- `buyer_note`, `buyer_phone`, `otp_challenge_id`, `otp_code`, `guest_verification_token`

Query params:
- none

Success response (HTTP 200 / 201):
- schema response is a generic object

Error responses:
- `400`: invalid reveal request
- `403`: reveal not allowed

React notes:
- this is the property-sale reveal initiation step, not the final unlock step
- do not send a buyer email; backend derives a Chapa-safe checkout email from the authenticated user or guest phone proof

### Read Property-Sale Seller Contact
Workflow reference: `REACT_WORKFLOW.md` Section 3
Method: `GET`
URL: `/api/v1/listing/property-sales/{id}/contact/`
Auth: yes (Bearer) / no
Roles: all

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- `CarSaleContact` payload reused for property-sale contact display

Error responses:
- `403`: reveal not unlocked or caller not entitled to the contact

React notes:
- do not expose this behind only client-side state; always fetch it after payment verification

## Section 6: Maps and Address (all roles)

### Autocomplete Address
Workflow reference: `REACT_WORKFLOW.md` Section 6
Method: `GET`
URL: `/api/v1/maps/autocomplete/`
Auth: no
Roles: all

Request body:
- none

Query params:
- place query text and session-token style params as supported by the map query serializer

Success response (HTTP 200):
- array of autocomplete results from the backend map layer

Common response fields:
- suggestion text
- `place_id`
- display address fragments

Error responses:
- `400`: invalid query

React notes:
- use this in the shared managed address field for company signup/apply and provider listing forms
- anonymous and authenticated callers use the same backend bridge and the same response shape
- backend provider is Geoapify-backed; React should not call Google directly for data

### Place Detail
Workflow reference: `REACT_WORKFLOW.md` Section 6
Method: `POST`
URL: `/api/v1/maps/place-detail/`
Auth: no
Roles: all

Request body:
- `place_id`: string - required
- `session_token`: string - required

Query params:
- none

Success response (HTTP 200):
- `lat`: decimal
- `lng`: decimal
- `formatted_address`: string
- `place_id`: string
- `components`: object - address components
  Common component fields:
  - `city`
  - `sub_city`
  - `region`
  - `country`
  - `postcode`

Error responses:
- `400`: invalid place request

React notes:
- use this after suggestion selection to build the final location payload
- this is public-safe for company signup and public discovery helpers; do not fork a company-only implementation

### Reverse Geocode
Workflow reference: `REACT_WORKFLOW.md` Section 6
Method: `GET`
URL: `/api/v1/maps/reverse-geocode/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `lat`, `lng`

Success response (HTTP 200):
- reverse-geocoded address object with formatted address and components

Error responses:
- `400`: invalid coordinates

React notes:
- useful for “use current pin” and manual map-adjust flows

## Section 7: Company Staff - Listing Management

### Read / Update Hotel Profile
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `GET` / `PATCH`
URL: `/api/v1/account/hotels/{id}/`
Auth: yes (Bearer) for patch / no for read
Roles: company_staff

Request body:
- patch uses hotel profile request shape

Query params:
- none

Success response (HTTP 200):
- hotel profile response with geo and verification fields

Error responses:
- `400`: invalid update payload
- `401`: unauthenticated for write
- `403`: not your hotel
- `404`: hotel not found

React notes:
- keep create/edit controls permission-aware; many staff roles may be read-only
- new hotels and hotel rooms default to active and unverified
- owner hotel management should use authenticated owner/managed views so inactive or unverified owned records are still visible

### Read / Update Room Listing
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `GET` / `PATCH`
URL: `/api/v1/listing/rooms/{id}/`
Auth: yes (Bearer) for patch / no for read
Roles: company_staff

Request body:
- patch uses `PatchedRoomListingRequest`

Query params:
- `check_in`, `check_out` - optional on read

Success response (HTTP 200):
- `RoomListingResponse` on read
- room listing object on patch

Error responses:
- `400`, `401`, `403`, `404`

React notes:
- patch only fields the UI actually edits; preserve backend-calculated fields

### Room Availability Matrix
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `GET`
URL: `/api/v1/listing/rooms/availability-matrix/`
Auth: yes (Bearer)
Roles: company_staff

Request body:
- none

Query params:
- room or workspace context as supported by the endpoint

Success response (HTTP 200):
- availability matrix response for room inventory control

Error responses:
- `401`, `403`

React notes:
- use for operational availability UI rather than public listing cards

### Guest House Profile / Room Management
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `GET` / `PATCH`
URL: `/api/v1/listing/guest-houses/{id}/` and `/api/v1/listing/guest-house-rooms/{id}/`
Auth: yes (Bearer) for patch / no for read
Roles: company_staff

Request body:
- patch uses guesthouse or guesthouse-room patch request schemas
- guesthouse patch accepts `is_active` so providers can activate or deactivate their own guest house

Query params:
- room detail supports `check_in`, `check_out`

Success response (HTTP 200):
- `GuestHouseProfileResponse` or `GuestHouseRoomResponse`

Error responses:
- `400`, `401`, `403`, `404`

React notes:
- use the room-level response for pricing-facing edits and preview context
- authenticated owners can retrieve their own inactive guest house records from the same detail endpoint for management flows
- new guest houses and guest-house rooms default to active and unverified
- owner/managed guest-house screens must show active, inactive, verified, and unverified owned records

### Guest House Availability Matrix
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `GET`
URL: `/api/v1/listing/guest-house-rooms/availability-matrix/`
Auth: yes (Bearer)
Roles: company_staff

Request body:
- none

Query params:
- operational filters as supported

Success response (HTTP 200):
- guesthouse availability matrix response

Error responses:
- `401`, `403`

React notes:
- use for workspace inventory controls

### Car Listing Management
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `GET` / `PATCH`
URL: `/api/v1/listing/cars/{id}/`
Auth: yes (Bearer) for patch / no for read
Roles: company_staff

Request body:
- patch uses `PatchedCarListingRequest`
- `business_license_document`: file|null - provider-owned business-license upload for self-drive cars that require business-license validation
- `with_driver_base_price`: decimal - provider-configured renter price for `with_driver`
- `without_driver_base_price`: decimal - provider-configured renter price for `without_driver`

Query params:
- none

Success response (HTTP 200):
- `CarListingResponse` or updated car listing object

Error responses:
- `400`, `401`, `403`, `404`

React notes:
- expose compliance fields like `requires_code_3` and `requires_business_license`
- when `rental_mode=without_driver` and `requires_business_license=true`, React must send `business_license_document` on create or before enabling that rule on edit
- managed owner responses can include `business_license_document` as the uploaded file URL; do not assume the public listing detail will expose that provider document
- renter-side price switching should read `with_driver_base_price` / `without_driver_base_price` or `pricing_by_rental_mode`

### Car Availability Update
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `PATCH`
URL: `/api/v1/listing/car-availabilities/{id}/update/`
Auth: yes (Bearer)
Roles: company_staff

Request body:
- availability patch fields from `PatchedCarAvailabilityUpdateRequest`

Query params:
- none

Success response (HTTP 200):
- `CarAvailabilityUpdate`

Error responses:
- `400`: invalid update
- `403`: not your availability row
- `404`: row not found

React notes:
- this is for operational inventory updates, not customer browsing

### Car Availability By Car And Date
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `GET`
URL: `/api/v1/listing/car-availabilities/by-car-and-date/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `car_listing`: uuid - required - target car listing id
- `start_date`: date - required - `YYYY-MM-DD`
- `end_date`: date - required - `YYYY-MM-DD` and must be after `start_date`
- `quantity`: integer - optional - requested units, defaults to `1`

Success response (HTTP 200):
- `CarAvailabilityByCarAndDateResponse`
- includes:
  - `car_listing`: object with `id`, `title`, `brand`, `model`, `base_price`
  - `search_period`: object with `start_date`, `end_date`
  - `quantity_requested`: integer
  - `availability`: object|null - current availability result for the requested range

Error responses:
- `400`: missing `car_listing`, missing dates, invalid date format, or `end_date <= start_date`

React notes:
- use this when the provider is managing availability for one selected car
- this is a read-only availability check; editing still happens through `/car-availabilities/{id}/update/`

### Car Availability By Dates
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `GET`
URL: `/api/v1/listing/car-availabilities/by-dates/`
Auth: no
Roles: all

Request body:
- none

Query params:
- `start_date`: date - required - `YYYY-MM-DD`
- `end_date`: date - required - `YYYY-MM-DD` and must be after `start_date`
- `quantity`: integer - optional - requested units, defaults to `1`

Success response (HTTP 200):
- `CarAvailabilityByDateRangeResponse`
- includes:
  - `search_period`: object with `start_date`, `end_date`
  - `quantity_requested`: integer
  - `available_cars_count`: integer
  - `available_cars`: array of objects with:
    - `car_listing_id`
    - `title`
    - `brand`
    - `model`
    - `base_price`
    - `availability`: object|null

Error responses:
- `400`: missing dates, invalid date format, or `end_date <= start_date`

React notes:
- use this for provider-side availability browsing across multiple cars in one date range
- the endpoint returns only cars whose availability check reports `is_available=true`

### Workspace Bookings
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `GET`
URL: `/api/v1/listing/bookings/workspace-bookings/` and `/api/v1/listing/guesthouse-bookings/workspace-bookings/`
Auth: yes (Bearer)
Roles: company_staff

Request body:
- none

Query params:
- workspace context from the authenticated user

Success response (HTTP 200):
- workspace booking list for the relevant domain

Error responses:
- `401`, `403`

React notes:
- use these for front-desk and staff operational dashboards

### Event Space Terms Management
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `GET` / `POST` / `PATCH` / `DELETE`
URL:
- `GET/POST /api/v1/listing/terms/event-space/{event_space_id}/`
- `GET /api/v1/listing/terms/event-space/{event_space_id}/history/`
- `PATCH /api/v1/listing/terms/{id}/`
- `DELETE /api/v1/listing/terms/{id}/`
- `POST /api/v1/listing/terms/{id}/publish/`
- `POST /api/v1/listing/terms/{id}/archive/`
Auth: mixed
Roles: company_staff

Request body:
- create draft: `title`, `content`, optional `effective_date`, optional `notes`
- patch draft: same fields, all optional

Success response:
- public current-terms `GET` returns active `TermsAndConditions` for the event space resolution chain
- provider `POST` and lifecycle actions return management records with:
  - `id`, `scope_type`, `scope_id`
  - `title`, `content`, `version`
  - `status`, `is_active`
  - `effective_date`, `created_at`, `updated_at`, `published_at`, `archived_at`
  - `created_by`
- history `GET` returns paginated management records

Error responses:
- `403`: unrelated company, front desk, or regular user cannot manage this scope
- `404`: no active terms for public read, or missing scope/record for management flows

React notes:
- `/terms/event-space/{id}/` can fall back to hotel terms, then company terms, if the event space has no active published terms
- use `scope_type` and `scope_id` from the returned record to label the real source of the terms in UI
- draft/history/publish/archive remain exact event-space management operations and do not mutate hotel/company terms directly
- QA label expectations:
  - `scope_type=event_space` -> `Event Space Terms`
  - `scope_type=hotel` -> `Hotel Terms`
  - `scope_type=company` -> `Company Terms`
- QA fallback expectations:
  - before an event-space draft is published, public current-terms can still resolve to hotel/company fallback
  - after archiving an active event-space record, current-terms can fall back again to hotel/company
  - React should always render the label from the latest response, not from the provider management screen state

## Section 8: Individual Owner - Listing Management

### Create / Update Property Listing
Workflow reference: `REACT_WORKFLOW.md` Section 5
Method: `POST` / `PATCH`
URL: `/api/v1/listing/properties/` and `/api/v1/listing/properties/{id}/`
Auth: yes (Bearer)
Roles: individual_owner

Request body:
- `title`: string - required on create
- `description`: string - optional
- `images`: array - required on create
- `base_price`: decimal|null
- `currency`: string
- `individual_owner`: uuid|null
- `company`: uuid|null
- `address`: object - required
- `property_type`: enum - required
- `bedrooms`: integer - required
- `bathrooms`: integer - required
- `square_meters`: decimal - required
- `is_furnished`: boolean
- `place_id`: string - writeOnly
- `session_token`: string - writeOnly

Query params:
- none

Success response (HTTP 201 / 200):
- `PropertyListingResponse`

Error responses:
- `400`: invalid property payload
- `401`: unauthenticated
- `403`: not your listing

React notes:
- `place_id` and `session_token` are the React-side map-input bridge for create flows
- new property-rental listings default to active and unverified

### Create / Update Car Sale Listing
Workflow reference: `REACT_WORKFLOW.md` Section 5
Method: `POST` / `PATCH`
URL: `/api/v1/listing/car-sales/` and `/api/v1/listing/car-sales/{id}/`
Auth: yes (Bearer)
Roles: company / individual_owner

Request body:
- uses `CarSaleListingRequest` / `PatchedCarSaleListingRequest`
- includes listing basics, sale details, seller contact, images, and address/place metadata
- `is_active`: optional boolean; new listings default to active and owners may toggle visibility independently of verification

Query params:
- none

Success response (HTTP 201 / 200):
- `CarSaleListingManagedResponse` with verification/activation state and the owner's stored seller contact

Error responses:
- `400`, `401`, `403`

React notes:
- write flows should keep seller contact private in UI previews
- fetch the owner record with `managed=true` to prefill seller contact; omitted contact fields on PATCH preserve their stored values
- verification is admin-controlled trust metadata and does not determine public visibility; only `is_active` controls visibility

### Create / Update / Delete Property Sale Listing
Workflow reference: `REACT_WORKFLOW.md` Section 5
Method: `POST` / `PATCH` / `DELETE`
URL: `/api/v1/listing/property-sales/` and `/api/v1/listing/property-sales/{id}/`
Auth: yes (Bearer)
Roles: company, individual_owner, admin

Request body:
- `POST`: uses `PropertySaleListingRequest`
- `PATCH`: uses `PatchedPropertySaleListingRequest`
- includes address and place metadata plus sale descriptors, including seller contact fields on managed write flows
- `DELETE`: no body

Query params:
- none

Success response (HTTP 201 / 200 / 204):
- `POST` / `PATCH`: `PropertySaleListingManagedResponse`
- `DELETE`: `204 No Content`

Error responses:
- `400`, `401`, `403`
- `404`: foreign or missing property-sale record on scoped update/delete

React notes:
- new property-sale listings default to active and unverified; show verification as trust metadata, not as visibility state
- fetch the owner record with `managed=true` to prefill seller contact; omitted contact fields on PATCH preserve their stored values

### Verification Status Fields
Workflow reference: `REACT_WORKFLOW.md` Section 5
Method: `GET`
URL: listing detail responses across `/rooms/{id}/`, `/guest-houses/{id}/`, `/guest-house-rooms/{id}/`, `/cars/{id}/`, `/car-sales/{id}/`, `/properties/{id}/`, `/property-sales/{id}/`, `/event-spaces/{id}/`
Auth: mixed by endpoint
Roles: all

Request body:
- none

Query params:
- endpoint-specific

Success response (HTTP 200):
- `is_verified`: boolean
- `verified_at`: datetime|null
- `verified_by`: uuid|null
- `verification_note`: string|null

Error responses:
- endpoint-specific `404` when listing not found

React notes:
- these fields are additive and stable across listing families

## Section 9: Individual Owner - Financial

### Owner Ledger List
Workflow reference: `REACT_WORKFLOW.md` Section 5
Method: `GET`
URL: `/api/v1/payment/ledger/`
Auth: yes (Bearer)
Roles: individual_owner

Request body:
- none

Query params:
- `page`, `page_size`
- `payout_status`: `pending`, `paid`, `failed`, `na`
- `search`
- `status`: `pending`, `success`, `failed`, `cancelled`

Success response (HTTP 200):
- paginated `OwnerPaymentTransaction`

Per result:
- `id`, `tx_ref`, `amount`, `currency`, `status`
- `payment_method`
- `receipt_url`
- `created_at`
- `booking_type`
- `booking_reference`
- `listing_title`
- `customer_name`
- `booking_dates`
- `owner_price`
- `service_fee`
- `tax_amount`
- `tax_rate`
- `grand_total`
- `tax_liability_status`
- `payout_status`
- `metadata`

Error responses:
- `401`: unauthenticated
- `403`: role not allowed

React notes:
- there is no dedicated tax ledger endpoint in the current schema
- tax visibility for owners comes from these ledger fields

### Owner Ledger Detail
Workflow reference: `REACT_WORKFLOW.md` Section 5
Method: `GET`
URL: `/api/v1/payment/ledger/{id}/`
Auth: yes (Bearer)
Roles: individual_owner

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- `OwnerPaymentTransaction`

Error responses:
- `401`, `403`, `404`

React notes:
- use detail screens for receipt links and line-by-line financial explanation

### Subaccount Setup / Read
Workflow reference: `REACT_WORKFLOW.md` Section 5
Method: `POST` / `GET`
URL: `/api/v1/payment/subaccounts/` and `/api/v1/payment/subaccounts/me/`
Auth: yes (Bearer)
Roles: individual_owner

Request body:
- `bank_code`: string - required
- `account_number`: string - required
- `business_name`: string - required
- `account_name`: string - required
- `owner_type`: enum - optional for admin scenarios
- `owner_id`: uuid - optional for admin scenarios
- `split_type`: enum - optional
- `split_value`: decimal - optional
- `allow_overwrite`: boolean - optional

Query params:
- none

Success response (HTTP 200 / 201):
- `owner_type`
- `owner_id`
- `chapa_subaccount_id`
- `split_type`
- `split_value`
- `split_config_active`

Error responses:
- `400`: invalid bank or split config
- `401`: unauthenticated
- `403`: not allowed

React notes:
- split fields are configuration, not immediate payment outcomes

## Section 10: Individual Owner - Compliance

### Read My Agreement Status
Workflow reference: `REACT_WORKFLOW.md` Section 5
Method: `GET`
URL: `/api/v1/account/profile/agreement/`
Auth: yes (Bearer)
Roles: individual_owner

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- `status`: enum - `pending`, `signed`, `revoked`
- `signed_at`: datetime|null
- `agreement_version`: string
- `agreement_document`: file URL|null

Error responses:
- `401`: unauthenticated
- `403`: not an owner profile flow

React notes:
- show this prominently on owner dashboards
- property-rental booking is allowed only when the owner has a signed agreement with an uploaded document
- there is no owner self-sign endpoint in the allowed React scope

### Read Agreement By Owner Id
Workflow reference: `REACT_WORKFLOW.md` Section 5
Method: `GET`
URL: `/api/v1/account/individual-owners/{id}/agreement/`
Auth: yes (Bearer)
Roles: individual_owner

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- `status`
- `signed_at`
- `agreement_version`
- `agreement_document`

Error responses:
- `401`, `403`, `404`

React notes:
- use this only when the owner dashboard already knows its owner-profile id

## Section 11: Promotions (all roles)

### Active Placements
Workflow reference: `REACT_WORKFLOW.md` Section 9
Method: `GET`
URL: `/api/v1/promotions/placements/`
Auth: no
Roles: all

Request body:
- none

Query params:
- none

Success response (HTTP 200):
- array of `PublicPlacement`

Per placement:
- `id`: uuid
- `slot_type`: enum
- `display_order`: integer
- `promoted_listing`: object|null with `id`, `title`, `thumbnail`, `category`, `rating`, `price_preview`, `currency`, `listing_type`
- `promoted_category`: object|null with `id`, `name`

Error responses:
- standard transport failures only; schema does not define custom error payloads here

React notes:
- `slot_type` should drive placement zones in home, search, or category pages

### Track Promotion Event
Workflow reference: `REACT_WORKFLOW.md` Section 9
Method: `POST`
URL: `/api/v1/promotions/track/`
Auth: no
Roles: all

Request body:
- `placement_id`: uuid - required
- `event_type`: string - required

Query params:
- none

Success response (HTTP 204):
- no response body

Error responses:
- `400`: invalid tracking request body

React notes:
- call this for click tracking; impression tracking can be product-specific

## Section 12: Payment (all flows)

### Payment Endpoints In React Scope
Workflow reference: `REACT_WORKFLOW.md` Section 7
Method: mixed
URL:
- `/api/v1/payment/initiate/`
- `/api/v1/payment/verify/{tx_ref}/`
- `/api/v1/payment/verify-public/{tx_ref}/`
- `/api/v1/payment/cancel/{tx_ref}/`
- `/api/v1/payment/subaccounts/`
- `/api/v1/payment/subaccounts/me/`

Auth:
- mixed by endpoint

Roles:
- regular_user / company_staff / individual_owner as applicable

React notes:
- hosted checkout is the default recommendation because it matches the current backend flow cleanly
- HTML checkout and inline JS are Chapa frontend integration styles, not separate backend REST endpoints
- if React adopts inline or HTML checkout later, keep using backend initiation and backend verification; never verify with Chapa directly from the browser

### Chapa Statuses and React Behavior
Workflow reference: `REACT_WORKFLOW.md` Section 7
Method: n/a
URL: n/a
Auth: n/a
Roles: all

Success response (HTTP n/a):
- `pending`: payment started but not yet verified
- `success`: payment verified; unlock the booking or reveal result
- `failed`: payment failed; show retry state where appropriate
- `cancelled`: pending payment was cancelled
- `refunded`: exceptional post-payment state
- `reversed`: exceptional post-payment state

Error responses:
- n/a

React notes:
- trust backend verification, not redirect URL parameters
- cancellation is not a refund flow
- receipt display depends on `receipt_url`

## Section 13: Admin Verification Display

The React app should display verification metadata but should not call admin-only verify endpoints in the current scoped integration.

Verification fields present on listing responses:
- `is_verified`
- `verified_at`
- `verified_by`
- `verification_note`

Admin-only verify/unverify endpoints do exist for multiple listing families, but they are excluded from this guide because they are admin-only and outside the allowed scope for this document.

React notes:
- show trust state consistently on cards and details
- activation and verification are separate product concepts

## Appendix A: Role Permission Matrix

| Endpoint group | Public | Regular user | Company staff | Individual owner |
| --- | --- | --- | --- | --- |
| `/api/v1/auth/token/`, `/auth/token/refresh/`, `/auth/otp/*` | Yes | Yes | Yes | Yes |
| `/api/v1/auth/me/`, `/account/users/me/`, `/account/location/` | No | Yes | Yes | Yes |
| Discovery endpoints `/listing/feed/`, `/search/`, `/nearby/`, `/within-bounds/`, `/map-pins/` | Yes | Yes | Yes | Yes |
| Listing detail endpoints across public families | Yes | Yes | Yes | Yes |
| Booking create and preview endpoints | Yes | Yes | No direct company use | Owner only where applicable to owned operations |
| Booking read/cancel for own bookings | No | Yes | Limited by workspace/ownership | Limited by ownership |
| Contact reveal request/read | Yes | Yes | No normal use | Possible for owner self-checks but not typical |
| Maps helper endpoints `/api/v1/maps/*` | Yes | Yes | Yes | Yes |
| Workspace booking endpoints | No | No | Yes | No |
| Owner ledger and subaccounts | No | No | Sometimes company-side equivalent exists separately | Yes |
| Owner agreement endpoints | No | No | No | Yes |
| Promotions placements and tracking | Yes | Yes | Yes | Yes |

## Appendix B: All Error Codes and React Behavior

| Code | Meaning | Typical shape | React behavior |
| --- | --- | --- | --- |
| `400` | validation or business-rule failure | field-error object or generic object | show inline errors and preserve user input |
| `401` | unauthenticated | generic auth object | clear tokens and redirect to login |
| `403` | authenticated but forbidden | generic object or `{detail}` | show permission state, do not crash |
| `404` | missing resource | generic object or `{detail}` | show not-found page or inline missing-state |
| `409` | conflict in some operational flows | generic object | show conflict message and reload relevant state |
| `500` | server failure | generic server error | show fallback error UI and retry path |

## Appendix C: Field Reference

Current field and contract notes React should follow:

- `formatted_address`, `latitude`, `longitude`, and `place_id` are the live location-display fields across listing families
- listings may have null coordinates temporarily because async geocoding can complete after save
- `challenge_token` and `cooldown_seconds` are now part of OTP responses
- `receipt_url` is the current receipt field to render after verified payment
- `tax_amount`, `tax_rate`, `grand_total`, and `tax_liability_status` are additive payment fields React must support
- `workspace` on auth/profile responses is the contract field React should use for company-side routing
- map provider migration is backend-only; React keeps using backend endpoints and should not depend on Google-specific backend behavior

## Appendix D: Breaking Change Register

These are the current contract changes React must already handle from `API_CONTRACT_CHANGELOG.md`.

| Date | Change | React impact |
| --- | --- | --- |
| 2026-06-13 | Discovery endpoints gained listing type filters for `event_space`, `car_rental`, and `property_sales` | expose these filters in web search and discovery |
| 2026-06-13 | Backend maps provider changed to Geoapify | no endpoint change; keep using backend REST only |
| 2026-06-12 | Listing serializers gained `latitude`, `longitude`, `formatted_address`, `place_id` | handle null and non-null geo fields in cards, detail, and map views |
| 2026-06-12 | Owner agreement endpoints and agreement status were added | show owner agreement state in the owner dashboard |
| 2026-06-11 | Promotions module and public placements were added | render promoted content blocks and tracking |
| 2026-06-11 | OTP responses gained `challenge_token` and `cooldown_seconds` | update OTP UX and resend timers |
| 2026-06-11 | Payment responses gained `tax_amount`, `tax_rate`, `grand_total`, `tax_liability_status` | show tax-aware payment breakdowns |
| 2026-06-10 to 2026-06-11 | Car sales, property sales, and property-rental booking endpoints were added | implement contact-reveal and property-rental flows in React |
| 2026-06-14 | Subaccount endpoints were added | enable owner/vendor payout setup screens |
| 2026-06-14 | `receipt_url` was added to payment transaction responses | show receipt actions after successful payment |

## Missed Routes

These routes are onboarding flows that are easy to miss when wiring the React app. Keep them separate from the main section flow so they stand out during implementation.

### Company Registration
Workflow reference: `REACT_WORKFLOW.md` Section 2
Method: `POST`
URL: `/api/v1/account/companies/`
Auth: no
Roles: all

Request body:
- `email`: string - optional - company account email
- `first_name`: string - required
- `last_name`: string - required
- `password`: string - required
- `confirm_password`: string - required
- `name`: string - required - company name
- `license`: file - required - company license document
- `logo`: file - optional
- `category`: string - required
- `description`: string - optional
- `phone`: string - required
- `tin`: string - optional
- `business_license_number`: string - optional
- `address`: object or JSON string - required - flexible address payload
  Preferred Geoapify payload:
  `{"place_id":"...","session_token":"..."}`
  Manual fallback payload:
  `{"street_line1":"...","city":"...","country":"Ethiopia","sub_city":"...","state":"...","postal_code":"...","latitude":...,"longitude":...}`

Success response (HTTP 201):
- company profile payload using `CompanyProfileResponse`
- `verification_required`: string - usually `phone`
- `phone_verification_required`: boolean
- `otp_challenge_id`: uuid
- `otp_expires_at`: datetime
- `otp_purpose`: string

Error responses:
- `400`: validation errors, duplicate user data, invalid address, or missing role configuration

React notes:
- this is the direct public company sign-up route
- the response includes OTP metadata, so React should route the user into verification after a successful create
- send the request as multipart form data because it includes files and a nested address payload
- when the user selects an address from Geoapify autocomplete, send `address.place_id` and `address.session_token` instead of manually collecting sub-city/state/postal fields
- backend now derives `street_line1`, `city`, `sub_city`, `state`, `postal_code`, `latitude`, and `longitude` from the selected place when those manual fields are omitted

### Company Apply
Workflow reference: `REACT_WORKFLOW.md` Section 4
Method: `POST`
URL: `/api/v1/account/companies/apply/`
Auth: yes (Bearer)
Roles: company_staff / individual_owner / other authenticated users allowed by backend

Request body:
- `name`: string - required - company name
- `license`: file - required - company license document
- `address`: object or JSON string - required - flexible address payload
  Preferred Geoapify payload:
  `{"place_id":"...","session_token":"..."}`
  Manual fallback payload:
  `{"street_line1":"...","city":"...","country":"Ethiopia","sub_city":"...","state":"...","postal_code":"...","latitude":...,"longitude":...}`
- `phone`: string - required
- `logo`: file - optional
- `category`: string - required
- `description`: string - optional

Success response (HTTP 201):
- company profile payload using `CompanyProfileResponse`

Error responses:
- `400`: validation errors or duplicate company profile on the same user
- `401`: unauthenticated

React notes:
- this is the authenticated company application route
- the created profile is stored with `PENDING` status until admin approval
- use this path when an already signed-in user applies for a company account instead of creating a fresh login
- use the same Geoapify-selected address payload here as public company signup; do not require manual sub-city/state entry after autocomplete


