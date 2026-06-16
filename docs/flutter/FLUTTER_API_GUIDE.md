# Flutter API Guide
# Backend: Django REST Framework + SimpleJWT
# Schema: /api/schema/swagger-ui/
# Last updated: 2026-06-15

This file is the Flutter-facing technical API reference.

Rules for using this guide:
- request and response fields below are sourced from `schema.yaml`
- where `schema.yaml` only declares a free-form JSON map, that is called out explicitly
- business meaning lives in [FLUTTER_WORKFLOW.md](/docs/flutter/FLUTTER_WORKFLOW.md)
- admin-only and React-only endpoints are intentionally excluded

Error body note:
- some non-2xx responses are declared in the schema only as free-form JSON maps
- Flutter should treat these as either field-error dictionaries or `{ "detail": "..." }`

## Section 1: Authentication

### Current User
Workflow reference: FLUTTER_WORKFLOW.md Section 2
Method: GET
URL: `/api/v1/auth/me/`
Auth required: yes (Bearer token)

Success response (200):
- `id`: uuid
- `email`: email
- `first_name`: string
- `last_name`: string
- `phone`: string or null
- `phone_verified`: boolean
- `phone_verified_at`: datetime or null
- `last_known_lat`: decimal string or null
- `last_known_lng`: decimal string or null
- `location_updated_at`: datetime or null
- `location_permission_granted`: boolean
- `is_active`: boolean
- `role`: structured role value or null
  - `id`: uuid
  - `name`: string
  - `code`: string
  - `created_at`: datetime
  - `updated_at`: datetime
- `workspace`: structured workspace value or null
  - `id`: string
  - `name`: string
  - `workspace_type`: string or null

Error responses:
- `401`: token missing or invalid

Flutter notes:
- use this after login, signup verification, and app relaunch

### Phone Password Login
Workflow reference: FLUTTER_WORKFLOW.md Section 2
Method: POST
URL: `/api/v1/auth/token/`
Auth required: no

Request body:
- `phone`: string - required in practice for the current phone-first login flow
- `password`: string - required

Success response (200):
- `refresh`: string
- `access`: string
- `role`: string or null, optional
- `company`: structured profile summary or null, optional
  - `id`: uuid
  - `name`: string
- `individual_owner`: structured profile summary or null, optional
  - `id`: uuid
  - `name`: string
- `workspace`: structured workspace value or null, optional
  - `id`: string
  - `name`: string
  - `workspace_type`: string or null

Error responses:
- `401`: invalid phone or password

Flutter notes:
- treat this as the primary credential login
- store both access and refresh tokens

### Token Refresh
Workflow reference: FLUTTER_WORKFLOW.md Section 2
Method: POST
URL: `/api/v1/auth/token/refresh/`
Auth required: no

Request body:
- `refresh`: string - required

Success response (200):
- `access`: string
- `refresh`: string may be present depending on rotation settings

Error responses:
- `401`: refresh token invalid or expired

Flutter notes:
- if refresh fails, clear local auth state and route to login

### Logout
Workflow reference: FLUTTER_WORKFLOW.md Section 2
Method: POST
URL: `/api/v1/auth/logout/`
Auth required: no

Request body:
- `refresh`: string - required

Success response (200):
- empty body

Flutter notes:
- always clear local tokens even if the server returns a non-critical failure

### Registration
Workflow reference: FLUTTER_WORKFLOW.md Section 2
Method: POST
URL: `/api/v1/account/users/`
Auth required: no

Request body:
- `email`: email - optional
- `password`: string - required
- `confirm_password`: string - required
- `first_name`: string - optional
- `last_name`: string - optional
- `phone`: string - required by the Flutter phone-first product flow

Success response (201):
- `id`: uuid
- `email`: email
- `first_name`: string
- `last_name`: string
- `phone`: string or null
- `phone_verified`: boolean
- `phone_verified_at`: datetime or null
- `last_known_lat`: decimal string or null
- `last_known_lng`: decimal string or null
- `location_updated_at`: datetime or null
- `location_permission_granted`: boolean
- `is_active`: boolean
- `role`: structured role value or null; same fields as Current User
- `workspace`: structured workspace value or null; same fields as Current User
- `verification_required`: string, normally `phone`
- `phone_verification_required`: boolean
- `otp_challenge_id`: uuid
- `otp_expires_at`: datetime
- `otp_purpose`: string

Error responses:
- `400`: validation errors such as password mismatch or duplicate phone

Flutter notes:
- signup is not complete until OTP verification succeeds

## Section 2: OTP

### OTP Request
Workflow reference: FLUTTER_WORKFLOW.md Section 8
Method: POST
URL: `/api/v1/auth/otp/request/`
Auth required: no

Request body:
- `phone`: string - required
- `purpose`: string - optional, defaults to `login`

Success response (200):
- `success`: boolean
- `challenge_id`: uuid
- `challenge_token`: uuid
- `purpose`: string
- `expires_at`: datetime
- `cooldown_seconds`: integer
- `phone`: string

Error responses:
- `400`: invalid phone or throttled request

Flutter notes:
- use `challenge_token` as the main client-side handle
- display resend cooldown from `cooldown_seconds`

### OTP Verify
Workflow reference: FLUTTER_WORKFLOW.md Section 8
Method: POST
URL: `/api/v1/auth/otp/verify/`
Auth required: no

Request body:
- `challenge_id`: uuid - optional
- `challenge_token`: uuid - optional
- `code`: string - required
- `purpose`: string - optional, defaults to `login`

Success response (200):
- `success`: boolean
- `purpose`: string
- `user`: structured user value or null, optional; same fields as Current User
- `access`: string, optional
- `refresh`: string, optional
- `role`: string or null, optional
- `guest_verification_token`: string, optional
- `guest_history_transfer`: guest-history transfer summary, optional
  - `linked_counts`: map of history type to integer count
  - `already_linked_counts`: map of history type to integer count
  - `linked_total`: integer
  - `already_linked_total`: integer

Error responses:
- `400`: invalid, expired, or mismatched OTP payload

Flutter notes:
- show generic OTP failure copy
- do not branch UI on "wrong code" versus "expired code"

## Section 3: User Profile

### Current Profile
Workflow reference: FLUTTER_WORKFLOW.md Section 9
Method: GET
URL: `/api/v1/account/users/me/`
Auth required: yes (Bearer token)

Success response (200):
- `id`: uuid
- `email`: email
- `first_name`: string
- `last_name`: string
- `phone`: string or null
- `phone_verified`: boolean
- `phone_verified_at`: datetime or null
- `last_known_lat`: decimal string or null
- `last_known_lng`: decimal string or null
- `location_updated_at`: datetime or null
- `location_permission_granted`: boolean
- `is_active`: boolean
- `role`: structured role value or null; same fields as Current User
- `workspace`: structured workspace value or null; same fields as Current User

Error responses:
- `400`: field-error map or `{ "detail": "..." }`
- `401`: token missing or invalid

### Update Profile
Workflow reference: FLUTTER_WORKFLOW.md Section 9
Method: PATCH
URL: `/api/v1/account/users/me/`
Auth required: yes (Bearer token)

Request body:
- partial user profile fields
- send only fields the user changed

Success response (200):
- `UserResponse`

Error responses:
- `400`: field-error map or `{ "detail": "..." }`
- `401`: token missing or invalid

Flutter notes:
- partial update only; send changed fields

### Delete My Account
Workflow reference: FLUTTER_WORKFLOW.md Section 9
Method: DELETE
URL: `/api/v1/account/users/me/`
Auth required: yes (Bearer token)

Success response (200):
- `UserResponse`

Error responses:
- `400`: field-error map or `{ "detail": "..." }`
- `401`: token missing or invalid

### Store User Location
Workflow reference: FLUTTER_WORKFLOW.md Section 9
Method: POST
URL: `/api/v1/account/location/`
Auth required: yes (Bearer token)

Request body:
- `lat`: decimal string - required
- `lng`: decimal string - required
- `permission_granted`: boolean - required

Success response (200):
- `lat`: decimal string
- `lng`: decimal string
- `permission_granted`: boolean

Error responses:
- `400`: invalid coordinates
- `401`: token missing or invalid

Flutter notes:
- call this only after the user consents to sharing location

### Convert Guest History
Workflow reference: FLUTTER_WORKFLOW.md Section 9
Method: POST
URL: `/api/v1/account/users/me/convert-guest-bookings/`
Auth required: yes (Bearer token)

Request body:
- `otp_challenge_id`: uuid - optional
- `otp_code`: string - optional

Success response (200):
- `success`: boolean
- `phone`: string
- `verified_via`: string
- `linked_counts`: map of history type to integer count
- `already_linked_counts`: map of history type to integer count
- `linked_total`: integer
- `already_linked_total`: integer
- current contract tests confirm:
  - `success`
  - `phone`
  - `verified_via`
  - `linked_counts`
  - `already_linked_counts`
  - `linked_total`
  - `already_linked_total`

Error responses:
- `400`: guest conversion validation or verification failure
- `401`: token missing or invalid

### Currency List
Workflow reference: FLUTTER_WORKFLOW.md Section 3 and 4
Method: GET
URL: `/api/v1/core/currencies/`
Auth required: no

Success response (200):
- array of:
  - `code`: string
  - `name`: string

### Currency Rates
Workflow reference: FLUTTER_WORKFLOW.md Section 3 and 4
Method: GET
URL: `/api/v1/core/currencies/rates/`
Auth required: no

Success response (200):
- currency-rate map keyed by currency code
  - key: currency code such as `ETB` or `USD`
  - value: decimal exchange-rate string or number, depending on stored rate source

Error responses:
- `404`: rates not available

### Currency Convert
Workflow reference: FLUTTER_WORKFLOW.md Section 3 and 4
Method: POST
URL: `/api/v1/core/currency/convert/`
Auth required: no

Request body:
- `date`: date - required
- `base`: string - required
- `target`: string - required
- `amount`: decimal string - required

Success response (200):
- `status`: string
- `input_amount`: decimal string
- `base`: string
- `target`: string
- `converted_amount`: decimal string
- `rate_date`: date
- `rate_used`: decimal string

Error responses:
- `400`: invalid input
- `404`: missing rate
- `500`: conversion failure

## Section 4: Listing Discovery

### Discovery Feed
Workflow reference: FLUTTER_WORKFLOW.md Section 3
Method: GET
URL: `/api/v1/listing/feed/`
Auth required: no

Query params:
- `listing_type`: string - optional
- `page`: integer - optional

Success response (200):
- `count`: integer
- `total_pages`: integer
- `current_page`: integer
- `page_size`: integer
- `next`: string or null
- `previous`: string or null
- `results`: array of discovery listings

Discovery listing item fields:
- `id`: uuid
- `listing_type`: string
- `title`: string
- `description`: string
- `latitude`: decimal string or null
- `longitude`: decimal string or null
- `formatted_address`: string or null
- `place_id`: string or null
- `price_preview`: decimal string or null
- `currency`: string
- `thumbnail_url`: string or null
- `rating`: double or null
- `is_verified`: boolean
- `distance_km`: present in current feed behavior when proximity is active

Error responses:
- `400`: invalid query params; response is a field-error map or `{ "detail": "..." }`

Flutter notes:
- `latitude` and `longitude` are the map-rendering coordinates

### Nearby Listings
Workflow reference: FLUTTER_WORKFLOW.md Section 3
Method: GET
URL: `/api/v1/listing/nearby/`
Auth required: no

Query params:
- `lat`: number - required for nearby mode
- `lng`: number - required for nearby mode
- `radius_km`: number - optional
- `listing_type`: string - optional
- `page`: integer - optional

Success response (200):
- same paginated envelope as feed
- results include `distance_km`

Error responses:
- `400`: missing or invalid map query values

### Listings Within Bounds
Workflow reference: FLUTTER_WORKFLOW.md Section 3
Method: GET
URL: `/api/v1/listing/within-bounds/`
Auth required: no

Query params:
- `north`: number - required
- `south`: number - required
- `east`: number - required
- `west`: number - required
- `listing_type`: string - optional
- `page`: integer - optional

Success response (200):
- same paginated envelope as feed
- results use discovery listing shape

Error responses:
- `400`: invalid bounds

### Map Pins
Workflow reference: FLUTTER_WORKFLOW.md Section 3
Method: GET
URL: `/api/v1/listing/map-pins/`
Auth required: no

Query params:
- nearby mode:
  - `lat`: number
  - `lng`: number
  - `radius_km`: number
- bounds mode:
  - `north`: number
  - `south`: number
  - `east`: number
  - `west`: number
- shared:
  - `listing_type`: string

Success response (200):
- array of map pins:
  - `id`: uuid
  - `listing_type`: string
  - `latitude`: decimal string or null
  - `longitude`: decimal string or null
  - `title`: string
  - `price_preview`: decimal string or null
  - `thumbnail_url`: string or null
  - `rating`: double or null

Error responses:
- `400`: invalid map query

Flutter notes:
- map pins are intentionally lighter than full listing cards

### Search
Workflow reference: FLUTTER_WORKFLOW.md Section 3
Method: GET
URL: `/api/v1/listing/search/`
Auth required: no

Query params:
- `q`: string - optional
- `lat`: number - optional
- `lng`: number - optional
- `radius_km`: number - optional
- `listing_type`: string - optional
- `sort_by`: string - optional
- `page`: integer - optional

Success response (200):
- paginated envelope:
  - `count`
  - `total_pages`
  - `current_page`
  - `page_size`
  - `next`
  - `previous`
  - `results`
  - `search_center`
  - `applied_radius_km`

Search result item fields:
- `id`
- `listing_type`
- `title`
- `description`
- `latitude`
- `longitude`
- `formatted_address`
- `place_id`
- `price_preview`
- `currency`
- `thumbnail_url`
- `rating`
- `is_verified`
- `distance_km`

Error responses:
- `400`: invalid search query

### Search Suggestions
Workflow reference: FLUTTER_WORKFLOW.md Section 3
Method: GET
URL: `/api/v1/listing/search/suggestions/`
Auth required: no

Query params:
- `q`: string - required
- `listing_type`: string - optional
- `lat`: number - optional
- `lng`: number - optional
- `limit`: integer - optional

Success response (200):
- array of suggestions:
  - `id`: uuid
  - `listing_type`: string
  - `title`: string
  - `formatted_address`: string or null
  - `thumbnail_url`: string or null
  - `rating`: double or null
  - `price_preview`: decimal string or null
  - `distance_km`: double or null
  - `latitude`: decimal string or null
  - `longitude`: decimal string or null

Error responses:
- `400`: invalid search query

### Favorites
Workflow reference: FLUTTER_WORKFLOW.md Section 2 and 9

#### Registered Favorites List
Method: GET
URL: `/api/v1/favorites/`
Auth required: yes (Bearer token)

Query params:
- `page`: integer - optional
- `page_size`: integer - optional

Success response (200):
- paginated list of favorites
- item shape:
  - `id`: uuid
  - `object_id`: string
  - `content_type_display`: string
  - `snapshot`: free-form listing snapshot map
    - common keys: `title`, `subtitle`, `thumbnail_url`, `price_preview`, `currency`
  - `object`: free-form current listing data map for the favorited item
  - `created_at`: datetime

#### Registered Favorite Create / Toggle
Method: POST
URL: `/api/v1/favorites/` or `/api/v1/favorites/toggle/`
Auth required: yes (Bearer token)

Request body:
- `content_type`: string - required
- `object_id`: string - required

Success response:
- same favorite fields as Registered Favorites List

#### Guest Favorites List
Method: GET
URL: `/api/v1/favorites/guest/`
Auth required: no

Success response (200):
- array of guest favorite records:
  - `id`: uuid
  - `guest_phone`: string
  - `object_id`: string
  - `content_type_display`: string
  - `snapshot`: free-form listing snapshot map
  - `object`: free-form current listing data map for the favorited item
  - `created_at`: datetime

#### Guest Favorite Create / Toggle
Method: POST
URL: `/api/v1/favorites/guest/` or `/api/v1/favorites/guest/toggle/`
Auth required: no

Request body:
- `guest_phone`: string - required
- `content_type`: string - required
- `object_id`: string - required

Success response:
- same guest favorite fields as Guest Favorites List

## Section 5: Address and Maps

### Address Autocomplete
Workflow reference: FLUTTER_WORKFLOW.md Section 3
Method: GET
URL: `/api/v1/maps/autocomplete/`
Auth required: yes (Bearer token)

Query params:
- `input`: string - required
- `session_token`: string - required

Success response (200):
- array of:
  - `place_id`: string
  - `description`: string
  - `main_text`: string
  - `secondary_text`: string

Error responses:
- `400`: invalid input
- `401`: token missing or invalid

### Place Detail
Workflow reference: FLUTTER_WORKFLOW.md Section 3
Method: POST
URL: `/api/v1/maps/place-detail/`
Auth required: yes (Bearer token)

Request body:
- `place_id`: string - required
- `session_token`: string - required

Success response (200):
- `lat`: decimal string
- `lng`: decimal string
- `formatted_address`: string
- `place_id`: string
- `components`: structured address component value
  - `city`: string or null
  - `country`: string or null
  - `postcode`: string or null
  - `region`: string or null

Error responses:
- `400`: invalid place id or provider failure
- `401`: token missing or invalid

### Reverse Geocode
Workflow reference: FLUTTER_WORKFLOW.md Section 3
Method: GET
URL: `/api/v1/maps/reverse-geocode/`
Auth required: yes (Bearer token)

Query params:
- `lat`: decimal string - required
- `lng`: decimal string - required

Success response (200):
- `formatted_address`: string
- `components`: structured address component value
  - `city`: string or null
  - `country`: string or null
  - `postcode`: string or null
  - `region`: string or null

Error responses:
- `400`: invalid coordinates
- `401`: token missing or invalid

## Section 6: Hotel Listings and Booking

### Hotel List
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/account/hotels/`
Auth required: no

Query params:
- `category`: string - optional
- `page`: integer - optional
- `page_size`: integer - optional

Success response (200):
- paginated hotel profile list
- result item fields:
  - `id`: integer
  - `name`: string
  - `phone`: string
  - `category`: string
  - `description`: string
  - `stars`: integer
  - `address`: structured address value
    - `city`: string
    - `country`: string
    - `sub_city`: string
    - `street_line1`: string
    - `latitude`: decimal string or null
    - `longitude`: decimal string or null
    - `state`: string
    - `postal_code`: string
  - `images`: array
  - `facilities`: array

### Room List
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/rooms/`
Auth required: no

Query params:
- `hotel`: string - optional
- `check_in`: date - optional
- `check_out`: date - optional
- `page`: integer - optional
- `page_size`: integer - optional

Success response (200):
- paginated rooms
- room fields:
  - `images`
  - `title`
  - `hotel_id`
  - `description`
  - `base_price`
  - `currency`
  - `booking_forward_window_days`
  - `address`
  - `amenities`
  - `number_of_guests`
  - `total_units`
  - `bed_type`
  - `room_size_sqm`
  - `smoking_allowed`
  - `children_allowed`
  - `refundable`

### Room Detail
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/rooms/{id}/`
Auth required: no

Query params:
- `check_in`: date - optional
- `check_out`: date - optional

Success response (200):
- room listing detail fields:
  - `images`
  - `title`
  - `hotel_id`
  - `description`
  - `base_price`
  - `currency`
  - `booking_forward_window_days`
  - `address`
  - `amenities`
  - `number_of_guests`
  - `total_units`
  - `bed_type`
  - `room_size_sqm`
  - `smoking_allowed`
  - `children_allowed`
  - `refundable`

### Room Price Preview
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/rooms/{id}/price-preview/`
Auth required: no

Query params:
- `check_in`: date - required
- `check_out`: date - required

Success response (200):
- deprecated free-form room preview map
- prefer the room detail endpoint with `check_in` and `check_out`; detail can include a complete `price_quote`

Error responses:
- `400`: invalid or missing dates

### Hotel Booking Price Preview
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/bookings/price-preview/`
Auth required: no

Query params:
- `display_currency`: string - optional

Request body:
- `check_in_date`: date - required
- `check_out_date`: date - required
- `items`: array of booking item selections - required
  - each item contains the room/listing id and selected quantity
- `guest_phone`: string - optional for preview, used for first-booking fee-waiver checks

Success response (200):
- `nights`: integer
- `items`: array of price preview items
  - `id`: uuid
  - `title`: string
  - `units`: integer
  - `price_per_unit`: string
  - `subtotal`: decimal string
  - `breakdown`: array of daily price rows
    - `date`: date
    - `price_per_unit`: decimal string
    - `source`: string
    - `note`: string or null
- `totals`: structured price totals
  - `items_subtotal`: decimal string
  - `platform_fee`: decimal string
  - `platform_fee_percentage`: decimal string
  - `grand_total`: decimal string
  - `currency`: string
- `conversion`: conversion metadata or null; schema currently marks this as nullable provider-calculated data

Error responses:
- `400`: invalid booking draft

### Create Hotel Booking
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/bookings/`
Auth required: no

Request body:
- `items`: array - required
- `check_in_date`: date - required
- `check_out_date`: date - required
- `terms_accepted`: boolean - Flutter must send `true`
- `terms_version`: string - Flutter must send the accepted terms version
- `guest_first_name`: string - optional
- `guest_last_name`: string - optional
- `guest_email`: email - optional
- `guest_phone`: string - required
- `special_requests`: string - optional
- `payment_currency`: string enum - optional, allowed values `USD`, `ETB`
- `otp_challenge_id`: uuid - optional
- `otp_code`: string - optional
- `guest_verification_token`: string - optional

Success response (201):
- `id`
- `user`
- `booking_reference`
- `check_in_date`
- `check_out_date`
- `total_price`
- `total_room_cost`
- `total_addon_cost`
- `currency`
- `status`
- `items`
- `snapshot`
- `conversion`
- `is_resumable`
- `terms_accepted`
- `terms_version`
- `terms_accepted_at`
- `terms_content_snapshot`
- `terms_url`
- `is_legacy`
- `stay_total`
- `guest_first_name`
- `guest_last_name`
- `guest_email`
- `guest_phone`
- `special_requests`

Error responses:
- `400`: validation, availability, terms, or OTP failure
- `401`: not usually used for guest create
- `403`: role or ownership restriction if applicable

### View My Hotel Booking
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/bookings/{id}/`
Auth required: yes (Bearer token)

Success response (200):
- `Booking`
- key fields guaranteed by schema:
  - `items`
  - `check_in_date`
  - `check_out_date`
  - `currency`
  - `status`
  - `guest_first_name`
  - `guest_last_name`
  - `guest_email`
  - `guest_phone`
  - `special_requests`

Error responses:
- `401`: token missing or invalid
- `404`: booking not found

### Cancel Hotel Booking
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/bookings/{id}/cancel/`
Auth required: no for transport, but cancellation still requires valid ownership or guest proof

Request body:
- `reason`: string - optional
- `guest_phone`: string - optional for guest cancellation
- `otp_challenge_id`: uuid - optional for guest cancellation
- `otp_code`: string - optional for guest cancellation
- `guest_verification_token`: string - optional for guest cancellation
- for guest cancellation, include either an accepted verification token or OTP fields matching the booking phone

Success response (200):
- `BookingResponse`

Error responses:
- `400`: cancellation rejected
- `403`: wrong user or failed guest verification
- `404`: booking not found

### Hotel Booking Lookup
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/bookings/lookup/`
Auth required: no

Query params:
- `email`: string - optional
- `reference`: string - required

Success response (200):
- `BookingResponse`

Error responses:
- `404`: booking not found

### Shared Terms Endpoints
Workflow reference: FLUTTER_WORKFLOW.md Section 4

#### Terms List
Method: GET
URL: `/api/v1/listing/terms/`
Auth required: no

Success response (200):
- paginated list of:
  - `id`
  - `version`
  - `title`
  - `content`
  - `effective_date`
  - `is_active`
  - `created_at`
  - `updated_at`

#### Company Terms
Method: GET
URL: `/api/v1/listing/terms/company/{company_id}/`
Auth required: no

Success response (200):
- `id`
- `version`
- `title`
- `content`
- `effective_date`
- `is_active`
- `created_at`
- `updated_at`

Error responses:
- `404`: no active company terms

## Section 7: Guesthouse Listings and Booking

### Guesthouse List
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/guest-houses/`
Auth required: no

Query params:
- `search`: string - optional
- `page`: integer - optional
- `page_size`: integer - optional

Success response (200):
- paginated guesthouse profiles
- result fields include:
  - `id`
  - `title`
  - `description`
  - `images`
  - `address`
  - `phone`
  - `website`
  - `logo`

### Guesthouse Detail
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/guest-houses/{id}/`
Auth required: no

Success response (200):
- `id`
- `title`
- `description`
- `images`
- `latitude`
- `longitude`
- `formatted_address`
- `place_id`
- `amenities`
- `address`
- `rating`
- `facility`
- `is_favorite`
- `rooms`
- `phone`
- `website`
- `license`
- `logo`
- `is_verified`
- `verified_at`
- `verified_by`
- `verification_note`

### Guesthouse Booking Price Preview
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/guesthouse-bookings/price-preview/`
Auth required: no

Query params:
- `display_currency`: string - optional

Request body:
- `start_date`: date - required
- `end_date`: date - required
- `items`: array of guesthouse room selections - required
  - each item contains the guesthouse room id and selected quantity
- `guest_phone`: string - optional for preview, used for first-booking fee-waiver checks

Success response (200):
- same `PricePreviewResponse` fields as Hotel Booking Price Preview

### Create Guesthouse Booking
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/guesthouse-bookings/`
Auth required: no

Request body:
- `start_date`: date - required
- `end_date`: date - required
- `items`: array - required
- `terms_accepted`: boolean - Flutter must send `true`
- `terms_version`: string - Flutter must send the accepted terms version
- `guest_first_name`: string - optional
- `guest_last_name`: string - optional
- `guest_email`: email - optional
- `guest_phone`: string - required
- `special_requests`: string - optional
- `payment_currency`: string enum - optional, allowed values `USD`, `ETB`
- `is_walk_in`: boolean - optional
- `otp_challenge_id`: uuid - optional
- `otp_code`: string - optional
- `guest_verification_token`: string - optional

Success response (201):
- `id`
- `renter`
- `booking_reference`
- `start_date`
- `end_date`
- `total_price`
- `total_item_cost`
- `currency`
- `status`
- `conversion`
- `terms_accepted_at`
- `terms_content_snapshot`
- `terms_url`
- `is_legacy`
- `stay_total`
- `guest_first_name`
- `guest_last_name`
- `guest_email`
- `guest_phone`
- `special_requests`

### View Guesthouse Booking
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/guesthouse-bookings/{id}/`
Auth required: yes (Bearer token)

Success response (200):
- `GuestHouseBooking`

### Cancel Guesthouse Booking
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/guesthouse-bookings/{id}/cancel/`
Auth required: yes (Bearer token) in schema

Request body:
- `reason`: string - optional
- `guest_phone`: string - optional for guest cancellation
- `otp_challenge_id`: uuid - optional for guest cancellation
- `otp_code`: string - optional for guest cancellation
- `guest_verification_token`: string - optional for guest cancellation

Success response (200):
- `GuestHouseBooking`

### Guesthouse Booking Lookup
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/guesthouse-bookings/lookup/`
Auth required: no

Query params:
- `email`: string - optional
- `reference`: string - required

Success response (200):
- `GuestHouseBooking`

Error responses:
- `404`: booking not found

## Section 8: Property Rental Listings and Booking

### Property Rental List
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/properties/`
Auth required: no

Query params:
- `company`: uuid - optional
- `individual_owner`: uuid - optional
- `property_type`: string - optional
- `search`: string - optional
- `page`: integer - optional
- `page_size`: integer - optional

Success response (200):
- paginated property listing response list
- result fields include:
  - `id`
  - `title`
  - `description`
  - `images`
  - `latitude`
  - `longitude`
  - `formatted_address`
  - `place_id`
  - `base_price`
  - `currency`
  - `booking_forward_window_days`
  - `address`
  - `property_type`
  - `bedrooms`
  - `bathrooms`
  - `square_meters`
  - `is_furnished`
  - `conversion`
  - `is_verified`
  - `verified_at`
  - `verified_by`
  - `verification_note`

### Property Rental Detail
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/properties/{id}/`
Auth required: no

Success response (200):
- property rental listing detail fields:
  - `id`
  - `title`
  - `description`
  - `images`
  - `latitude`
  - `longitude`
  - `formatted_address`
  - `place_id`
  - `base_price`
  - `currency`
  - `booking_forward_window_days`
  - `address`
  - `property_type`
  - `bedrooms`
  - `bathrooms`
  - `square_meters`
  - `is_furnished`
  - `conversion`
  - `is_verified`
  - `verified_at`
  - `verified_by`
  - `verification_note`

### Property Rental Price Preview
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/property-rentals/bookings/price-preview/`
Auth required: no

Request body:
- `property_listing`: uuid - required
- `start_date`: date - required
- `end_date`: date - required
- `guest_phone`: string - optional for preview

Success response (200):
- same `PricePreviewResponse` fields as Hotel Booking Price Preview
- totals may later align with payment fields such as `tax_amount` and `grand_total` during checkout

Error responses:
- `400`: invalid dates or booking draft

### Create Property Rental Booking
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/property-rentals/bookings/`
Auth required: no

Request body:
- `property_listing`: uuid - required
- `start_date`: date - required
- `end_date`: date - required
- `terms_accepted`: boolean - required
- `terms_version`: string - required
- `guest_first_name`: string - optional
- `guest_last_name`: string - optional
- `guest_email`: email - optional
- `guest_phone`: string - required
- `special_requests`: string - optional
- `payment_currency`: string enum - optional, allowed values `USD`, `ETB`
- `otp_challenge_id`: uuid - optional
- `otp_code`: string - optional
- `guest_verification_token`: string - optional

Success response (201):
- `id`
- `renter`
- `booking_reference`
- `property_listing`
- `start_date`
- `end_date`
- `total_price`
- `total_item_cost`
- `currency`
- `status`
- `conversion`
- `terms_accepted`
- `terms_version`
- `terms_accepted_at`
- `terms_content_snapshot`
- `is_legacy`
- `guest_first_name`
- `guest_last_name`
- `guest_email`
- `guest_phone`
- `special_requests`
- `snapshot`
- `created_at`
- `updated_at`

Error responses:
- `400`: validation or availability failure
- `403`: compliance or access rule blocked the booking

Flutter notes:
- if the owner lacks an active compliance agreement, expect a `403`

### View Property Rental Booking
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/property-rentals/bookings/{id}/`
Auth required: yes (Bearer token)

Success response (200):
- `PropertyRentalBookingResponse`

Error responses:
- `403`: user is not allowed to see this booking

### Cancel Property Rental Booking
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/property-rentals/bookings/{id}/cancel/`
Auth required: yes (Bearer token)

Success response (200):
- `PropertyRentalBookingResponse`

Error responses:
- `400`: cancellation rejected
- `403`: wrong user

### Property Rental Guest OTP Request
Workflow reference: FLUTTER_WORKFLOW.md Section 8
Method: POST
URL: `/api/v1/listing/property-rentals/bookings/guest-otp/request/`
Auth required: no

Request body:
- `guest_phone`: string - required

Success response (201):
- `success`: boolean
- `challenge_id`: uuid
- `challenge_token`: uuid
- `purpose`: string
- `expires_at`: datetime
- `cooldown_seconds`: integer
- `guest_phone`: string, or `phone`: string depending on endpoint serializer

## Section 8b: Car Rentals

### Car Rental Listings
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/cars/`
Auth required: no

Query params:
- `brand`, `car_class`, `condition`, `fuel_type`, `listing_type`, `transmission`, `ordering`, `search`, `is_active`, `page`, `page_size`

Success response (200):
- paginated car listing response list

### Car Rental Detail
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/cars/{id}/`
Auth required: no

Success response (200):
- `id`
- `title`
- `description`
- `images`
- `latitude`
- `longitude`
- `formatted_address`
- `place_id`
- `base_price`
- `booking_forward_window_days`
- `is_active`
- `brand`
- `model`
- `year`
- `mileage`
- `fuel_type`
- `transmission`
- `condition`
- `listing_type`
- `rental_mode`
- `car_class`
- `quantity`
- `company`
- `seats`
- `individual_owner`
- `requires_code_3`
- `requires_business_license`
- `pre_rental_requirements`
- `availabilities`
- `current_availability`
- `conversion`
- `price_quote`
- `is_verified`

### Car Rental Price Preview
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/car-rentals/price-preview/`
Auth required: no

Query params:
- `display_currency`: string - optional

Request body:
- `start_date`: date - required
- `end_date`: date - required
- `rental_items`: array of car selections - required
  - each item contains the car listing id and selected quantity
- `guest_phone`: string - optional for preview, used for first-booking fee-waiver checks

Success response (200):
- same `PricePreviewResponse` fields as Hotel Booking Price Preview

Error responses:
- `400`: invalid draft
- `409`: availability conflict

### Create Car Rental
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/car-rentals/`
Auth required: no

Request body:
- `renter`: uuid - optional
- `start_date`: date - required
- `end_date`: date - required
- `currency`: string - optional
- `rental_items`: array - required
- `terms_accepted`: boolean - required
- `terms_version`: string - required
- `guest_first_name`: string - optional
- `guest_last_name`: string - optional
- `guest_email`: email - optional
- `guest_phone`: string - required
- `special_requests`: string - optional
- `otp_challenge_id`: uuid - optional
- `otp_code`: string - optional
- `guest_verification_token`: string - optional
- `renter_driver_license_number`: string - optional
- `renter_code_3_license_number`: string - optional
- `renter_business_license_number`: string - optional
- `payment_currency`: string enum - optional, allowed values `USD`, `ETB`

Success response (201):
- `id`
- `renter`
- `renter_name`
- `booking_reference`
- `start_date`
- `end_date`
- `total_price`
- `total_rental_cost`
- `currency`
- `status`
- `items_details`
- `created_at`
- `updated_at`
- `conversion`
- `terms_accepted_at`
- `terms_content_snapshot`
- `terms_url`
- `is_legacy`
- `stay_total`
- `guest_first_name`
- `guest_last_name`
- `guest_email`
- `guest_phone`
- `special_requests`
- `renter_driver_license_number`
- `renter_code_3_license_number`
- `renter_business_license_number`

### Car Rental Lookup
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: GET
URL: `/api/v1/listing/car-rentals/lookup/`
Auth required: no

Query params:
- `reference`: string - optional
- `guest_phone`: string - optional
- `guest_verification_token`: string - optional
- `otp_challenge_id`: uuid - optional
- `otp_code`: string - optional
- `email`: email - optional legacy path

Success response (200):
- `CarRental`

Error responses:
- `404`: rental not found

### Car Rental Extension Request
Workflow reference: FLUTTER_WORKFLOW.md Section 4
Method: POST
URL: `/api/v1/listing/car-rentals/{id}/request-extension/`
Auth required: no

Request body:
- `new_end_date`: date - required
- `guest_phone`: string - optional
- `otp_challenge_id`: uuid - optional
- `otp_code`: string - optional
- `guest_verification_token`: string - optional
- `payment_currency`: enum - optional

Success response (200):
- `booking_reference`
- `current_end_date`
- `new_end_date`
- `extra_days`
- `extension_subtotal`
- `platform_fee`
- `original_amount`
- `original_currency`
- `amount`
- `currency`
- `exchange_rate`
- `guest_verification_token`
- `extension_request_id`
- `status`
- `tx_ref`
- `checkout_url`

## Section 8c: Event Spaces

### Event Space List
Workflow reference: FLUTTER_WORKFLOW.md Section 1 and 3
Method: GET
URL: `/api/v1/listing/event-spaces/`
Auth required: no

Query params:
- `company`, `hotel`, `search`, `page`, `page_size`

Success response (200):
- paginated event space listing response list

### Event Space Detail
Workflow reference: FLUTTER_WORKFLOW.md Section 1 and 3
Method: GET
URL: `/api/v1/listing/event-spaces/{id}/`
Auth required: no

Success response (200):
- `id`
- `images`
- `latitude`
- `longitude`
- `formatted_address`
- `place_id`
- `title`
- `description`
- `number_of_guests`
- `base_price`
- `currency`
- `booking_forward_window_days`
- `amenities`
- `total_units`
- `space_type`
- `floor_area_sqm`
- `conversion`
- `price_quote`
- `is_verified`
- `verified_at`
- `verified_by`
- `verification_note`

## Section 9: Car Sales

### Car Sales List
Workflow reference: FLUTTER_WORKFLOW.md Section 5
Method: GET
URL: `/api/v1/listing/car-sales/`
Auth required: no

Query params:
- `brand`, `car_class`, `condition`, `fuel_type`, `transmission`, `ordering`, `search`, `is_active`, `page`, `page_size`

Success response (200):
- paginated car sale listing response list

### Car Sale Detail
Workflow reference: FLUTTER_WORKFLOW.md Section 5
Method: GET
URL: `/api/v1/listing/car-sales/{id}/`
Auth required: no

Success response (200):
- `id`
- `title`
- `description`
- `images`
- `latitude`
- `longitude`
- `formatted_address`
- `place_id`
- `base_price`
- `currency`
- `brand`
- `model`
- `year`
- `mileage`
- `fuel_type`
- `transmission`
- `condition`
- `car_class`
- `seats`
- `company`
- `individual_owner`
- `reveal_fee`
- `is_active`
- `is_verified`
- `verified_at`
- `verified_by`
- `verification_note`
- `reveal_state`
- `conversion`
- `created_at`
- `updated_at`

Flutter notes:
- seller contact fields are intentionally not present before unlock

### Car Sale Guest OTP Request
Workflow reference: FLUTTER_WORKFLOW.md Section 5 and 8
Method: POST
URL: `/api/v1/listing/car-sales/guest-otp/`
Auth required: no

Request body:
- `guest_phone`: string - required by the guest contact reveal OTP flow

Success response (201):
- `success`: boolean
- `challenge_id`: uuid
- `challenge_token`: uuid
- `purpose`: string
- `expires_at`: datetime
- `cooldown_seconds`: integer
- `guest_phone`: string, or `phone`: string depending on endpoint serializer

### Request Car Sale Contact Reveal
Workflow reference: FLUTTER_WORKFLOW.md Section 5
Method: POST
URL: `/api/v1/listing/car-sales/{id}/request-contact/`
Auth required: no

Request body:
- `buyer_note`: string - optional
- `buyer_phone`: string - optional
- `otp_challenge_id`: uuid - optional
- `otp_code`: string - optional
- `guest_verification_token`: string - optional

Success response (200 or 201):
- already-unlocked response can include:
  - `success`
  - `contact_unlocked`
  - `reveal_request`
  - `contact`
  - `guest_verification_token`
- newly-started payment response can include:
  - `success`
  - `checkout_url`
  - `tx_ref`
  - `reveal_request`
  - `guest_verification_token`

Error responses:
- `400`: invalid reveal request or missing verification
- `403`: forbidden, including owner self-reveal

Flutter notes:
- this is the payment gate handoff
- the schema intentionally allows either checkout fields or already-unlocked fields; store the returned values and refresh reveal state after payment

### Get Unlocked Car Sale Contact
Workflow reference: FLUTTER_WORKFLOW.md Section 5
Method: GET
URL: `/api/v1/listing/car-sales/{id}/contact/`
Auth required: no

Success response (200):
- `listing_id`: uuid
- `request_id`: uuid
- `status`: string
- `seller_contact_name`: string
- `seller_phone`: string
- `seller_email`: email - optional
- `off_platform_notice`: string

Error responses:
- `403`: contact still locked or user/guest not allowed

## Section 10: Property Sales

### Property Sales List
Workflow reference: FLUTTER_WORKFLOW.md Section 6
Method: GET
URL: `/api/v1/listing/property-sales/`
Auth required: no

Query params:
- `is_active`, `is_furnished`, `ordering`, `page`, `page_size`, `property_type`, `search`

Success response (200):
- paginated property sale listing response list

### Property Sale Detail
Workflow reference: FLUTTER_WORKFLOW.md Section 6
Method: GET
URL: `/api/v1/listing/property-sales/{id}/`
Auth required: no

Success response (200):
- `id`
- `title`
- `description`
- `images`
- `latitude`
- `longitude`
- `formatted_address`
- `place_id`
- `base_price`
- `currency`
- `company`
- `individual_owner`
- `address`
- `property_type`
- `bedrooms`
- `bathrooms`
- `square_meters`
- `land_size_square_meters`
- `is_furnished`
- `reveal_fee`
- `is_active`
- `is_verified`
- `verified_at`
- `verified_by`
- `verification_note`
- `reveal_state`
- `conversion`
- `created_at`
- `updated_at`

Flutter notes:
- seller contact fields are intentionally not present before unlock

### Property Sale Guest OTP Request
Workflow reference: FLUTTER_WORKFLOW.md Section 6 and 8
Method: POST
URL: `/api/v1/listing/property-sales/guest-otp/`
Auth required: no

Request body:
- `guest_phone`: string - required by the guest contact reveal OTP flow

Success response (201):
- `success`: boolean
- `challenge_id`: uuid
- `challenge_token`: uuid
- `purpose`: string
- `expires_at`: datetime
- `cooldown_seconds`: integer
- `guest_phone`: string, or `phone`: string depending on endpoint serializer

### Request Property Sale Contact Reveal
Workflow reference: FLUTTER_WORKFLOW.md Section 6
Method: POST
URL: `/api/v1/listing/property-sales/{id}/request-contact/`
Auth required: no

Request body:
- same schema as car-sale contact request:
  - `buyer_note`
  - `buyer_phone`
  - `otp_challenge_id`
  - `otp_code`
  - `guest_verification_token`

Success response (200 or 201):
- already-unlocked response can include:
  - `success`
  - `contact_unlocked`
  - `reveal_request`
  - `contact`
  - `guest_verification_token`
- newly-started payment response can include:
  - `success`
  - `checkout_url`
  - `tx_ref`
  - `reveal_request`
  - `guest_verification_token`
- current contract tests confirm one stable unlocked case contains:
  - `contact_unlocked`
  - `reveal_request`
  - `contact`

Error responses:
- `400`: invalid reveal request
- `403`: forbidden

### Get Unlocked Property Sale Contact
Workflow reference: FLUTTER_WORKFLOW.md Section 6
Method: GET
URL: `/api/v1/listing/property-sales/{id}/contact/`
Auth required: no

Success response (200):
- same `CarSaleContact` shape currently used by schema:
  - `listing_id`
  - `request_id`
  - `status`
  - `seller_contact_name`
  - `seller_phone`
  - `seller_email`
  - `off_platform_notice`

Error responses:
- `403`: contact still locked

## Section 11: Payment

### Initiate Payment
Workflow reference: FLUTTER_WORKFLOW.md Section 7
Method: POST
URL: `/api/v1/payment/initiate/`
Auth required: no

Request body:
- `booking_id`: uuid - required
- `booking_type`: string - optional, defaults to hotel booking
- `email`: email - optional
- `first_name`: string - optional
- `last_name`: string - optional
- `amount`: decimal string - optional; send only as a client-side expectation, server still derives and verifies the real amount
- `currency`: string - optional

Success response (200):
- `success`: boolean
- `message`: string
- `checkout_url`: uri or null
- `tx_ref`: string
- `calculated_amount`: string
- `payment_currency`: string
- `exchange_rate`: string
- `original_amount`: string
- `original_currency`: string
- `owner_price`: string or null
- `service_fee`: string or null
- `tax_amount`: string or null
- `tax_rate`: string or null
- `grand_total`: string or null
- `tax_liability_status`: string or null

Error responses:
- `400`: invalid booking or unsupported payment request
- `403`: forbidden
- `404`: booking or reveal request not found

Flutter notes:
- open `checkout_url` in WebView or system browser
- do not mark the booking or reveal successful yet

### Verify Payment (Authenticated)
Workflow reference: FLUTTER_WORKFLOW.md Section 7
Method: GET
URL: `/api/v1/payment/verify/{tx_ref}/`
Auth required: yes (Bearer token)

Success response (200):
- `id`: uuid, optional
- `tx_ref`: string, optional
- `booking`: uuid or null, optional
- `amount`: decimal string, optional
- `currency`: string, optional
- `status`: string, optional
- `payment_method`: string or null, optional
- `chapa_transaction_id`: string or null, optional
- `receipt_url`: uri or null, optional
- `owner_price`: string or null, optional
- `service_fee`: string or null, optional
- `tax_amount`: decimal string or null, optional
- `tax_rate`: decimal string or null, optional
- `grand_total`: string or null, optional
- `tax_liability_status`: string or null, optional
- `metadata`: free-form payment metadata map, optional
  - common keys can identify booking/reveal type, source flow, or provider context
- `created_at`: datetime, optional
- `updated_at`: datetime, optional
- `chapa_verification`: free-form Chapa verification map
  - common keys from Chapa include `status`, `message`, and provider `data`

Error responses:
- `400`: invalid `tx_ref` or verification failure
- `403`: transaction does not belong to the caller

Flutter notes:
- use this for signed-in user payment refresh

### Verify Payment (Public)
Workflow reference: FLUTTER_WORKFLOW.md Section 7
Method: GET
URL: `/api/v1/payment/verify-public/{tx_ref}/`
Auth required: no

Success response (200):
- same fields as Verify Payment (Authenticated)
- `chapa_verification`: free-form Chapa verification map is always present

Error responses:
- `400`: invalid or unresolvable transaction reference

Flutter notes:
- use this for guest payment follow-up and post-checkout polling

### Callback URL Handling
Workflow reference: FLUTTER_WORKFLOW.md Section 7

Flutter does not call the Chapa callback directly.

What Flutter does:
1. receive `checkout_url` from `/api/v1/payment/initiate/`
2. open Chapa checkout
3. after redirect or app resume, call a backend verify endpoint
4. trust backend verification result only

Payment status notes from `Agents/PAYMENT_SERVICE.md`:
- `success`
- `pending`
- `failed`
- `cancelled`
- `refunded`
- `reversed`

## Section 12: OTP and Booking Verification

### Hotel Booking Guest OTP Request
Workflow reference: FLUTTER_WORKFLOW.md Section 8
Method: POST
URL: `/api/v1/listing/bookings/guest-otp/request/`
Auth required: no

Request body:
- `guest_phone`: string - required

Success response (201):
- `success`: boolean
- `challenge_id`: uuid
- `challenge_token`: uuid
- `purpose`: string
- `expires_at`: datetime
- `cooldown_seconds`: integer
- `guest_phone`: string, or `phone`: string depending on endpoint serializer

### Guesthouse Booking Guest OTP Request
Workflow reference: FLUTTER_WORKFLOW.md Section 8
Method: POST
URL: `/api/v1/listing/guesthouse-bookings/guest-otp/request/`
Auth required: no

Request body:
- `guest_phone`: string - required

Success response (201):
- `success`: boolean
- `challenge_id`: uuid
- `challenge_token`: uuid
- `purpose`: string
- `expires_at`: datetime
- `cooldown_seconds`: integer
- `guest_phone`: string, or `phone`: string depending on endpoint serializer

### Car Rental Guest OTP Request
Workflow reference: FLUTTER_WORKFLOW.md Section 8
Method: POST
URL: `/api/v1/listing/car-rentals/guest-otp/request/`
Auth required: no

Request body:
- `guest_phone`: string - required

Success response (201):
- `success`: boolean
- `challenge_id`: uuid
- `challenge_token`: uuid
- `purpose`: string
- `expires_at`: datetime
- `cooldown_seconds`: integer
- `guest_phone`: string, or `phone`: string depending on endpoint serializer

### Booking Verification Inputs
Workflow reference: FLUTTER_WORKFLOW.md Section 8

The following fields appear across guest booking and guest reveal create endpoints:
- `otp_challenge_id`: uuid
- `otp_code`: string
- `guest_verification_token`: string

Flutter notes:
- use `otp_challenge_id` plus `otp_code` immediately after OTP entry
- use `guest_verification_token` for subsequent guest self-service calls when the backend returns one

## Section 13: Promotions

### Public Placements
Workflow reference: FLUTTER_WORKFLOW.md Section 10
Method: GET
URL: `/api/v1/promotions/placements/`
Auth required: no

Success response (200):
- array of public placements:
  - `id`: uuid
  - `slot_type`: string
  - `display_order`: integer
  - `promoted_listing`: structured promoted listing snapshot or null
  - `promoted_category`: structured promoted category snapshot or null

`promoted_listing` fields:
- `id`: uuid
- `title`: string
- `thumbnail`: uri or null
- `category`: string
- `rating`: double or null
- `price_preview`: decimal string
- `currency`: string
- `listing_type`: string

`promoted_category` fields:
- `id`: string
- `name`: string

### Track Promotion Event
Workflow reference: FLUTTER_WORKFLOW.md Section 10
Method: POST
URL: `/api/v1/promotions/track/`
Auth required: no

Request body:
- `placement_id`: uuid - required
- `event_type`: string - required

Success response (204):
- empty body

Flutter notes:
- fire this on impression or click based on product UX rules

## Section 14: Notifications

### Notifications List
Workflow reference: FLUTTER_WORKFLOW.md Section 13
Method: GET
URL: `/api/v1/notifications/`
Auth required: yes (Bearer token)

Query params:
- `created_after`: datetime - optional
- `created_before`: datetime - optional
- `is_read`: boolean - optional
- `notification_type`: string - optional
- `priority`: string - optional
- `ordering`: string - optional
- `page`: integer - optional
- `page_size`: integer - optional

Success response (200):
- paginated notifications
- notification item fields:
  - `id`
  - `notification_type`
  - `notification_type_display`
  - `title`
  - `message`
  - `action_url`
  - `metadata`
  - `is_read`
  - `read_at`
  - `priority`
  - `priority_display`
  - `created_at`
  - `delivered_in_app`
  - `delivered_email`
  - `delivered_sms`
  - `delivered_push`
  - `email_sent_at`
  - `sms_sent_at`
  - `push_sent_at`

### Mark Notification Read
Workflow reference: FLUTTER_WORKFLOW.md Section 13
Method: PATCH
URL: `/api/v1/notifications/{id}/mark-read/`
Auth required: yes (Bearer token)

Request body:
- no body is normally needed from Flutter

Success response (200):
- `Notification`

Error responses:
- `404`: notification not found

### Mark All Notifications Read
Workflow reference: FLUTTER_WORKFLOW.md Section 13
Method: POST
URL: `/api/v1/notifications/mark-all-read/`
Auth required: yes (Bearer token)

Success response (200):
- notification mark-all summary for the current user
  - schema currently leaves keys free-form; expected practical keys include count/read totals

### Notification Preferences
Workflow reference: FLUTTER_WORKFLOW.md Section 13
Method: GET / PUT
URL: `/api/v1/notifications/preferences/`
Auth required: yes (Bearer token)

Request body for PUT:
- `email_preferences`: notification-type preference map - optional, example `{ "payment_success": true, "booking_confirmed": false }`
- `in_app_preferences`: notification-type preference map - optional, example `{ "payment_success": true, "booking_confirmed": true }`
- `sms_preferences`: notification-type preference map - optional, example `{ "payment_success": true, "booking_confirmed": false }`
- `push_preferences`: notification-type preference map - optional, example `{ "payment_success": true, "booking_confirmed": true }`
- `email_enabled`: boolean - optional
- `sms_enabled`: boolean - optional
- `push_enabled`: boolean - optional

Success response (200):
- `email_preferences`: notification-type preference map
- `in_app_preferences`: notification-type preference map
- `sms_preferences`: notification-type preference map
- `push_preferences`: notification-type preference map
- `email_enabled`: boolean
- `sms_enabled`: boolean
- `push_enabled`: boolean

### Unread Count
Workflow reference: FLUTTER_WORKFLOW.md Section 13
Method: GET
URL: `/api/v1/notifications/unread-count/`
Auth required: yes (Bearer token)

Success response (200):
- unread count summary for the current user
  - schema currently leaves keys free-form; expected practical key is `unread_count`

### Notification Summary
Workflow reference: FLUTTER_WORKFLOW.md Section 13
Method: GET
URL: `/api/v1/notifications/summary/`
Auth required: yes (Bearer token)

Success response (200):
- notification summary for the current user
  - schema currently leaves keys free-form; expected practical keys group totals by read status, type, and priority

## Appendix A: All Error Codes

Global HTTP handling for Flutter:
- `400`: invalid user input, availability failure, OTP failure, or business-rule rejection
- `401`: missing, expired, or invalid token
- `403`: authenticated but not allowed, or sensitive guest flow not verified
- `404`: resource missing or transaction/booking reference not found
- `409`: conflict, currently used by car-rental preview availability conflict
- `500`: generic server-side failure

Payment provider notes from `Agents/PAYMENT_SERVICE.md`:
- Chapa initialization can fail on invalid currency, reused `tx_ref`, bad split config, or API/account issues
- Chapa verification can report not found, not paid yet, or environment/key mismatch

## Appendix B: All Chapa Payment Statuses

Statuses documented in `Agents/PAYMENT_SERVICE.md`:
- `success`: payment completed; Flutter should refresh booking or reveal state and show success
- `pending`: payment not final; show pending and allow recheck
- `failed`: payment failed; show retry path
- `cancelled`: payment or checkout was cancelled; return safely to the previous screen
- `refunded`: exceptional support state, not a normal user journey
- `reversed`: exceptional support state, not a normal user journey
- `PENDING`: provider-side pending variant used in direct-charge docs; treat like pending

## Appendix C: Flutter Contract Test Coverage

The following endpoints are covered in `tests/integration/test_flutter_contracts.py` and should be treated as especially stable for Flutter integration:

- `/api/v1/auth/me/`
- `/api/v1/auth/otp/request/`
- `/api/v1/auth/otp/verify/`
- `/api/v1/account/users/`
- `/api/v1/account/users/me/convert-guest-bookings/`
- `/api/v1/account/hotels/`
- `/api/v1/account/location/`
- `/api/v1/core/currencies/`
- `/api/v1/core/currencies/rates/`
- `/api/v1/core/currency/convert/`
- `/api/v1/listing/rooms/{id}/`
- `/api/v1/listing/car-sales/{id}/`
- `/api/v1/listing/car-sales/{id}/contact/`
- `/api/v1/listing/property-sales/{id}/`
- `/api/v1/listing/property-sales/{id}/request-contact/`
- `/api/v1/listing/nearby/`
- `/api/v1/listing/map-pins/`
- `/api/v1/listing/feed/`
- `/api/v1/listing/search/`
- `/api/v1/listing/search/suggestions/`
- `/api/v1/maps/autocomplete/`
- `/api/v1/maps/place-detail/`
- `/api/v1/listing/properties/`
- `/api/v1/listing/property-rentals/bookings/`
- `/api/v1/listing/property-rentals/bookings/price-preview/`
- `/api/v1/payment/verify-public/{tx_ref}/`
- `/api/v1/favorites/`
- `/api/v1/favorites/guest/`
- `/api/v1/notifications/`
- `/api/v1/notifications/preferences/`
- `/api/v1/promotions/placements/`

Notable additional domains already present in the backend but not deeply contract-tested in this file:
- hotel booking create/cancel payload variants
- guesthouse booking full lifecycle
- car-rental extension initiation
- notification summary and unread-count object details
