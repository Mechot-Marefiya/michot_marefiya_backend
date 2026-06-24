# API Contract Changelog

[2026-06-24] TASK-102 - Public Shared Maps Bridge
Modified endpoints: GET /api/v1/maps/autocomplete/
                    POST /api/v1/maps/place-detail/
                    GET /api/v1/maps/reverse-geocode/
Change type: NON-BREAKING auth relaxation plus additive response field
Auth change: endpoints are now public-safe for anonymous and authenticated callers
Stable response contract preserved for existing authenticated callers
Additive response field: `components.sub_city`
React action required: yes - stop assuming auth is required for shared managed address flows
Flutter action required: yes - stop assuming auth is required for shared managed address flows

[2026-06-13] TASK-607 - All Listing Family Map Coverage
Modified: existing listing discovery, map pin, feed, search, and search suggestion endpoints
Change type: NON-BREAKING additive listing_type filters
New listing_type filters: event_space, car_rental, property_sales
Existing listing_type filters unchanged: hotel, guesthouse, property_rental, car_sales, all
Flutter action required: yes - expose filters for event spaces, car rentals, and property sales
React action required: yes - expose filters for event spaces, car rentals, and property sales

[2026-06-13] TASK-606 - Google Maps To Geoapify Migration
Modified: backend map provider implementation only
Change type: NON-BREAKING provider migration
Provider: Geoapify is now the only active backend maps provider
Deprecated: Google Maps backend settings and active service logic
Endpoint contract: unchanged
Existing endpoints preserved:
GET /api/v1/maps/autocomplete/
POST /api/v1/maps/place-detail/
GET /api/v1/maps/reverse-geocode/
GET /api/v1/listing/nearby/
GET /api/v1/listing/within-bounds/
GET /api/v1/listing/map-pins/
GET /api/v1/listing/feed/
GET /api/v1/listing/search/
GET /api/v1/listing/search/suggestions/
POST /api/v1/account/location/
Stable fields preserved: latitude, longitude, formatted_address,
                         place_id, address_components, distance_km,
                         search_center, applied_radius_km
Flutter action required: no - continue using backend REST endpoints
React action required: no - continue using backend REST endpoints
Operational note: provide GEOAPIFY_API_KEY in backend environment;
                  never expose it to clients

[2026-06-12] TASK-402 - Add Coordinates To All Listing Models
Modified models: apps.core.GeoLocatedModel, apps.listing.BaseListing subclasses,
                 apps.account.HotelProfile, apps.account.User
New fields exposed read-only on listing detail/list serializers:
latitude, longitude, formatted_address, place_id
Change type: NON-BREAKING additive model and serializer update
Flutter action required: yes - handle null map coordinates in listing cards/details
React action required: yes - handle null map coordinates in listing cards/details

[2026-06-12] TASK-401 - Google Maps Service Layer
New shared service: services/maps.py
Settings added: GOOGLE_MAPS_API_KEY, GOOGLE_MAPS_GEOCODING_URL,
                GOOGLE_MAPS_PLACES_AUTOCOMPLETE_URL,
                GOOGLE_MAPS_PLACE_DETAIL_URL,
                DEFAULT_PROXIMITY_RADIUS_KM, MAX_PROXIMITY_RADIUS_KM,
                GEOCODING_CACHE_TTL, PROXIMITY_CACHE_TTL, MAP_PINS_CACHE_TTL
Change type: NEW shared backend integration layer
Flutter action required: yes - consume backend map helpers and proximity data
React action required: yes - consume backend map helpers and proximity data

[2026-06-11] TASK-308 - Platform Admin Dashboard Metrics
New endpoints: GET /api/v1/analytics/admin/overview/
               GET /api/v1/analytics/admin/revenue/
               GET /api/v1/analytics/admin/payout-failures/
Auth: admin only
Change type: NEW additive admin analytics endpoints
Flutter action required: no - admin dashboard is React only
React action required: yes - platform admin dashboard screens

[2026-06-12] TASK-309 - Owner Compliance Agreement Tracking
Modified: owner profile response (additive agreement status)
Change type: NON-BREAKING additive embedding
New endpoints: GET/POST/PATCH /api/v1/account/individual-owners/{pk}/agreement/
               POST /api/v1/account/individual-owners/{pk}/agreement/sign/
               POST /api/v1/account/individual-owners/{pk}/agreement/revoke/
               GET /api/v1/account/profile/agreement/
Flutter action required: yes - show agreement status on owner profile screen
React action required: yes - admin agreement management and owner profile display

[2026-06-12] TASK-310 - Transaction Monitoring and Dispute Triage
New endpoints: GET /api/v1/payment/admin/transactions/
               GET /api/v1/payment/admin/transactions/{pk}/
               POST /api/v1/payment/admin/transactions/{pk}/dispute/open/
               PATCH /api/v1/payment/admin/transactions/{pk}/dispute/
               POST /api/v1/payment/admin/transactions/{pk}/dispute/resolve/
Auth: admin only
Change type: NON-BREAKING additive payment admin surface
Flutter action required: no - admin surface is React only
React action required: yes - transaction monitoring dashboard and dispute management UI

[2026-06-11] TASK-307 - Promotional Advertising Module
New app: apps.promotions
New endpoints: GET/POST /api/v1/promotions/campaigns/
               GET/PUT/PATCH/DELETE /api/v1/promotions/campaigns/{pk}/
               GET/POST /api/v1/promotions/campaigns/{pk}/placements/
               GET /api/v1/promotions/placements/
               POST /api/v1/promotions/track/
Change type: NEW additive module
Flutter action required: yes - render promoted listing slots in search and category screens
React action required: yes - admin campaign and placement management, render promoted slots

[2026-06-13] TASK-406 - Search Improvement With Radius Support
New endpoints: GET /api/v1/listing/search/
               GET /api/v1/listing/search/suggestions/
Change type: NON-BREAKING additive search/discovery fields
New fields: distance_km, latitude, longitude, formatted_address,
            search_center, applied_radius_km
Approach: Haversine formula with DecimalField lat/lng; no PostGIS or GeoDjango
Google API status: implemented; live geocoding/backfill pending valid billing-enabled API key
Flutter action required: yes - use unified search and suggestions with optional map context
React action required: yes - use unified search and suggestions with optional map context

[2026-06-11] TASK-306 - Admin Listing Verification Actions
Modified: all listing and hotel detail/list responses
Change type: NON-BREAKING additive fields
New fields: verification_note
Modified endpoints: POST /api/v1/account/hotels/{pk}/verify/
                    POST /api/v1/account/hotels/{pk}/unverify/
                    POST /api/v1/listing/rooms/{pk}/verify/
                    POST /api/v1/listing/rooms/{pk}/unverify/
                    POST /api/v1/listing/guest-houses/{pk}/verify/
                    POST /api/v1/listing/guest-houses/{pk}/unverify/
                    POST /api/v1/listing/guest-house-rooms/{pk}/verify/
                    POST /api/v1/listing/guest-house-rooms/{pk}/unverify/
                    POST /api/v1/listing/cars/{pk}/verify/
                    POST /api/v1/listing/cars/{pk}/unverify/
                    POST /api/v1/listing/car-sales/{pk}/verify/
                    POST /api/v1/listing/car-sales/{pk}/unverify/
                    POST /api/v1/listing/properties/{pk}/verify/
                    POST /api/v1/listing/properties/{pk}/unverify/
                    POST /api/v1/listing/property-sales/{pk}/verify/
                    POST /api/v1/listing/property-sales/{pk}/unverify/
                    POST /api/v1/listing/event-spaces/{pk}/verify/
                    POST /api/v1/listing/event-spaces/{pk}/unverify/
Flutter action required: yes - show verified badge and optional verification note
React action required: yes - show verified badge, optional verification note, and admin verify controls

[2026-06-11] TASK-305 - Reusable OTP Service Layer
Modified: existing auth OTP responses and shared guest booking OTP flow
Change type: NON-BREAKING additive fields plus async delivery
Modified endpoints: POST /api/v1/auth/otp/request/
                    POST /api/v1/auth/otp/verify/
                    existing listing guest OTP request endpoints
New response fields: challenge_token, cooldown_seconds
Flutter action required: yes - read `challenge_token` alias and cooldown metadata
React action required: yes - read `challenge_token` alias and cooldown metadata

[2026-06-11] TASK-304 - 15% Tax Handling
Modified: existing payment endpoint responses
Change type: NON-BREAKING additive fields
New fields: tax_amount, tax_rate, grand_total,
            tax_liability_status
Flutter action required: yes - display tax breakdown
React action required: yes - display tax breakdown
New endpoint: skipped - scoped request excluded tax ledger endpoint

[2026-06-10] TASK-301 — Car Sales Connector Flow
New endpoints: GET/POST /api/v1/listing/car-sales/
               GET /api/v1/listing/car-sales/{pk}/
               POST /api/v1/listing/car-sales/{pk}/request-contact/
               GET /api/v1/listing/car-sales/{pk}/contact/
Flutter action required: yes — contact reveal state machine
React action required: yes — car sales listing page

[2026-06-11] TASK-302 — Property Sales Connector Flow
New endpoints: GET/POST /api/v1/listing/property-sales/
               GET /api/v1/listing/property-sales/{pk}/
               POST /api/v1/listing/property-sales/{pk}/request-contact/
Flutter action required: yes — property contact reveal state
React action required: yes — property sales listing page

[2026-06-11] TASK-303 — Property Rental Booking Flow
New endpoints: POST /api/v1/listing/property-rentals/bookings/
               GET  /api/v1/listing/property-rentals/bookings/{pk}/
               POST /api/v1/listing/property-rentals/bookings/{pk}/cancel/
               POST /api/v1/listing/property-rentals/bookings/price-preview/
Flutter action required: yes — property rental booking screens
React action required: yes — property rental booking page
[2026-06-12] TASK-403 — Async Geocoding On Listing Save
Changed: existing listing save flows now enqueue async geocoding
         for address-bearing listings after successful save
New artifact: `apps/listing/management/commands/geocode_existing_listings.py`
Flutter action required: yes — handle asynchronously populated coordinates
React action required: yes — handle asynchronously populated coordinates

[2026-06-12] TASK-404 — Proximity And Discovery Endpoints
New endpoints: GET /api/v1/listing/nearby/
               GET /api/v1/listing/within-bounds/
               GET /api/v1/listing/map-pins/
               GET /api/v1/listing/feed/
Flutter action required: yes — render proximity, viewport, map pin, and feed discovery states
React action required: yes — render proximity, viewport, map pin, and feed discovery states

[2026-06-14] TASK-805 - Chapa Subaccount Registration API
New endpoints: POST /api/v1/payment/subaccounts/
               GET /api/v1/payment/subaccounts/me/
Change type: NON-BREAKING additive endpoints
Flutter action required: yes - vendor subaccount setup screen
React action required: yes - admin/vendor subaccount setup screen

[2026-06-14] TASK-808 - Chapa Receipt Access
Modified: existing payment transaction responses
Change type: NON-BREAKING additive field
New field: receipt_url
Flutter action required: yes - display Chapa receipt link after successful payment
React action required: yes - display Chapa receipt link after successful payment
