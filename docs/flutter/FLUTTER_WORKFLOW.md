# Flutter App Workflow
# For: Regular users (guests and registered)
# Last updated: 2026-06-15

## 1. App Overview

This app is a customer-facing marketplace for discovering and paying for:
- hotel stays
- guesthouse stays
- event spaces
- car rentals
- property rentals
- car-sale contact reveals
- property-sale contact reveals

It is designed for the Ethiopian market, uses ETB-first pricing, and sends users through Chapa for paid actions.

This app is not:
- the listing-owner console
- the admin console
- the place where company onboarding, listing moderation, tax operations, or campaign management are done

User types in Flutter:
- Guest: can browse, save, search, and complete many flows without creating an account, but must use phone verification for sensitive guest actions
- Registered user: has account-based access, profile, notifications, booking history, and payment-linked identity

API note:
- this file explains product behavior and business rules
- use `schema.yaml` as the live endpoint contract
- use `CODEBASE_MAP.md` for backend structure and auth expectations

## 2. Authentication Flows

### 2a. Guest browsing (no auth required)

Guests can:
- browse public listings across all supported categories
- open listing detail pages
- use home feed, nearby discovery, search, suggestions, map pins, and viewport search
- use map-based discovery from public listing endpoints
- save listings as guest favorites by phone identity
- start guest booking flows
- start guest contact-reveal flows for car sales and property sales
- complete payment as a guest

Guests do not need login for browsing, but they do need phone verification for sensitive guest actions like:
- guest bookings
- guest contact reveals
- some guest self-service access flows

Actions that require login:
- loading the full account profile
- storing user location on the account
- in-app notification center
- account-based favorites
- registered-user booking history and profile management
- token refresh and logout lifecycle
- converting guest history into an account

Important product rule:
- guest access is supported, but phone identity is the trust anchor
- the app should never treat anonymous guest actions as completely identity-free

### 2b. Registration

Registration is phone-first.

Required fields:
- phone
- password
- password confirmation

Common optional or profile-style fields:
- first name
- last name
- email

Signup flow:
1. User enters phone and password
2. Backend creates an inactive account and sends OTP by SMS
3. User enters OTP code
4. OTP verification activates the account and returns auth tokens

Business rules:
- email is optional, not primary
- duplicate phone numbers are blocked
- a registered user gets only 3 phone changes total
- after each phone change there is a 7-day cooldown before another change
- if guest history already exists for that phone, successful signup verification can link that history to the new account

Implementation reference:
- `schema.yaml` auth endpoints
- `CODEBASE_MAP.md > Authentication and Permissions`

### 2c. Login

Do not design the customer app around email/password login.

Current customer-facing login options are:
- phone + password
- phone OTP login

Recommended app UX:
- make phone the primary identifier everywhere
- keep email out of the core login path

Phone + password flow:
1. User enters phone and password
2. Backend returns access token and refresh token
3. Flutter stores both securely
4. Flutter loads current profile and app state

OTP login flow:
1. User enters phone
2. OTP is sent by SMS
3. User enters code
4. Backend returns tokens on success

What happens after successful login:
- store access token
- store refresh token
- load user profile
- load favorites, notifications, and booking-related state

Implementation reference:
- `schema.yaml` auth endpoints

### 2d. Token refresh

Refresh when:
- access token expires
- backend returns a token-expired response and refresh is still available

If refresh fails:
- clear both tokens
- clear user-only memory state
- redirect to login

Do not silently keep the user in a half-authenticated state.

Implementation reference:
- `schema.yaml` token endpoints

### 2e. Logout

Logout flow:
- clear local access token
- clear local refresh token
- clear user-scoped cached state
- call the server-side logout flow when available so refresh token blacklisting is preserved

Implementation reference:
- `schema.yaml` logout endpoint

## 3. Listing Discovery

### 3a. Home feed

The home feed is the user’s general discovery surface.

What it should show:
- active listings only
- mixed listing types
- promoted placements where configured
- verification badge when available
- enough price context to help the user decide where to tap

When location permission is granted:
- the feed can become proximity-aware
- ordering can prefer nearby listings
- search and map experiences can include distance

When location is not granted:
- the app still works
- feed falls back to standard discovery ordering

Business rules:
- listings may show `Verified` or `Not Verified`
- unverified does not automatically mean hidden
- booking start dates are restricted by the forward-booking window
- default forward window is 5 days unless the listing allows a different value

Implementation reference:
- `schema.yaml` listing feed and nearby endpoints

### 3b. Search

Search supports:
- keyword search
- place-driven search
- nearby search
- filtered search by listing type

Recommended search UX:
1. User types a place or keyword
2. App shows suggestions while typing
3. User can refine by category and radius
4. Results can switch between list and map

Filters that matter most:
- listing type
- radius
- price
- rating
- location context

Expected result behavior:
- if location is known, results may include `distance_km`
- if location is not known, `distance_km` can be null
- search can still work without coordinates through keyword matching

Important UX note:
- the backend map/search layer is already provider-backed
- Flutter should consume backend search responses, not talk directly to the maps provider

Implementation reference:
- `schema.yaml` search, suggestions, and nearby endpoints

### 3c. Map view

Flutter is responsible for rendering the map.

Backend responsibilities:
- provide listing coordinates
- provide light map-pin payloads
- provide viewport-based listing results
- provide place autocomplete and place-detail resolution through backend APIs for authenticated users

Map behavior:
- listings with coordinates appear on the map
- listings without coordinates stay available in list views
- map pins should be lightweight
- when the user pans, reload based on bounds instead of reusing stale results forever

Important product rule:
- the backend is the source of truth for map discovery
- Flutter should not compute listing proximity on its own
- public discovery endpoints can power guest map browsing
- backend place-helper endpoints are currently authenticated, so guest address search should rely on public listing search until that contract changes

Implementation reference:
- `schema.yaml` map and listing discovery endpoints

### 3d. Listing detail

A listing detail page should show:
- title and media
- description
- category-specific attributes
- price context
- verification badge
- location summary
- map pin when coordinates are present
- favorite state
- booking or reveal action based on listing type

Verification:
- use `is_verified` for badge logic
- optionally show verification note if surfaced in the UI design

Pricing:
- price is not just a display number
- previews can include service fee, owner amount, tax, and grand total depending on flow
- the first booking tied to a phone number can waive the service fee
- add-ons do not receive service-fee markup

Property rental tax:
- tax appears only where applicable
- non-applicable flows should treat tax as not applicable, not as waived

Implementation reference:
- `schema.yaml` listing detail, price preview, and payment endpoints

## 4. Booking Flows

General booking pattern across booking domains:
1. User selects listing and dates
2. App requests price preview
3. App shows full pricing breakdown
4. User accepts terms
5. Booking is created in `pending`
6. User proceeds to payment
7. Booking becomes `confirmed` only after verified payment

Important business rules across booking types:
- phone number is required for every booking
- guest booking flows require guest OTP verification before final create
- availability is checked on create
- terms are snapshotted at booking time
- no refunds are supported
- cancellation releases availability when allowed

Implementation reference:
- `schema.yaml` booking and payment endpoints

### 4a. Hotel booking

Hotel booking user journey:
1. User opens a room or hotel detail
2. Selects check-in and check-out dates
3. Reviews preview and nightly breakdown
4. Accepts terms
5. Creates booking
6. Pays through Chapa
7. Sees confirmation only after payment verification succeeds

Business rules:
- forward booking window applies
- availability is enforced at create time
- total includes service fee only where applicable
- first booking by phone can waive service fee
- add-ons do not get service-fee markup
- cancelling does not create a refund

### 4b. Guesthouse booking

Guesthouse follows the same shape as hotel booking, with guesthouse-specific inventory.

Business rules:
- same OTP rule for guest checkout
- same pending to confirmed payment lifecycle
- same no-refund policy
- same date-window restriction

### 4c. Property rental booking

Property rental is a real booking flow, not a contact reveal.

User journey:
1. Open property rental listing
2. Select dates
3. Review preview
4. Accept terms
5. Create pending booking
6. Proceed to payment
7. Booking becomes confirmed after verified payment

Extra business rule for individual-owner rentals:
- if the owner does not have an active compliance agreement, booking must be blocked

Tax rule:
- property-rental payment responses can include tax fields
- tax applies only to qualifying individual-owner property-rental flows

### 4d. Booking management

Registered-user expectation:
- users should have a clear "My Bookings" area by booking type or unified booking history

Guest expectation:
- guest flows are supported, but access is verified by phone
- do not assume every guest history screen is the same across all listing families
- where guest self-service exists, Flutter should follow the verified-phone flow exposed by the backend contract

Cancellation:
- allowed only when the backend permits it
- if cancellation succeeds, availability is released back
- cancellation is not a refund event

Statuses users may see:
- `pending`: booking exists, payment or final confirmation not complete
- `confirmed`: paid and confirmed
- `cancelled`: cancelled and no longer active
- `walk_in`: staff-created offline-style venue booking, mostly relevant as a read-only label if exposed

Car-rental note:
- car rentals also support extension and reschedule-related flows
- added days only take effect after extension payment is confirmed

Implementation reference:
- `schema.yaml` booking history, guest lookup, cancellation, and car-rental extension endpoints

## 5. Car Sales Contact Reveal Flow

This is not a booking.

The platform only sells access to the seller's contact details.

User journey:
1. User opens a car-sale listing
2. Sees sale listing details and reveal price
3. If guest, verifies phone through reveal OTP flow
4. Requests contact reveal
5. Pays reveal fee through Chapa
6. After verified payment, contact becomes available
7. Buyer and seller continue off-platform

Business rules:
- contact data must never appear before verified payment
- listing owners cannot reveal their own contact through the buyer flow
- payment failure keeps contact locked
- stale reveal requests expire
- reveal fee is configurable by platform/admin rules

Reveal states users may encounter:
- requested
- payment initiated
- paid and revealed
- expired

Implementation reference:
- `schema.yaml` car-sales reveal and payment endpoints

## 6. Property Sales Contact Reveal Flow

Property sales follow the same connector model as car sales.

User journey:
1. Open property-sale listing
2. Review sale details and reveal price
3. If guest, verify phone
4. Request contact reveal
5. Complete payment
6. After verified payment, seller contact is unlocked

Business rules:
- the platform connects buyer and seller only
- property transaction itself happens off-platform
- contact never appears before payment verification
- expired reveal requests must be restarted

Implementation reference:
- `schema.yaml` property-sales reveal and payment endpoints

## 7. Payment Flow (Chapa)

This flow applies to:
- booking payments
- contact reveals
- car-rental extension payments

Standard user flow:
1. Backend prepares the payment
2. Flutter receives checkout URL and payment context
3. Flutter opens Chapa checkout
4. User completes or abandons payment
5. Chapa redirects or callback completes
6. Flutter asks backend for final verified status
7. Flutter shows success, pending, failure, or cancelled state

Important rule:
- never treat payment initiation as success
- only verified payment can unlock value

What Flutter should show by status:
- `success`: show confirmation and refresh the booking or reveal state
- `pending`: show pending state and allow recheck
- `failed`: show failure and allow retry
- `cancelled`: show cancelled state and route back safely
- `refunded`: not part of the standard customer journey because the platform is no-refund; treat as exceptional support state if ever returned

Money rules:
- no refunds on platform service payments
- walk-in venue payments do not carry platform commission
- add-ons are excluded from platform commission
- first booking by phone may waive the service fee
- property rental may show tax fields where applicable

Receipts:
- successful payments can expose a receipt URL
- Flutter should surface it where useful after success

Chapa test mode guidance:
- use only Chapa test numbers/cards in test mode
- test mode still sends webhooks and other provider-side events
- never assume live behavior without final live-key verification

Implementation reference:
- `schema.yaml` payment initiate, verify, webhook, and receipt fields

## 8. OTP Flow (Detailed)

OTP is a core trust mechanism in the customer app.

It is used for:
- OTP login
- signup verification
- password reset
- guest bookings
- guest contact reveals
- guest-history conversion

General OTP flow:
1. User submits phone and purpose
2. Backend returns challenge token and expiry
3. App shows OTP entry and countdown
4. User enters code
5. Backend verifies
6. App continues with the next step

What success can return:
- tokens for login/signup purposes
- guest verification token for guest-only flows
- profile/user info where relevant

Edge cases Flutter must handle:
- cooldown before requesting another code
- max-attempt lockout on the current challenge
- expiry requiring a new challenge
- generic failure messaging only

UX rule:
- never reveal whether the code was wrong, expired, or otherwise invalid in too much detail
- keep the error generic and actionable

Implementation reference:
- `schema.yaml` OTP request and verify endpoints

## 9. User Profile

Profile area should support:
- viewing current user details
- updating basic profile data
- phone change with policy-aware validation
- password reset/change flows
- location storage

Phone rules:
- changing phone resets verification state
- user can only change phone 3 times
- each change starts a 7-day cooldown

Location permission:
- ask clearly and only when useful
- if granted, store the location for better feed and discovery
- if denied, app still works without proximity personalization

Guest-to-user conversion:
- once a guest registers and verifies the same phone, their guest booking history and guest favorites can be linked to the new account

Implementation reference:
- `schema.yaml` profile, location, and guest-conversion endpoints

## 10. Promotions and Ads

Promotions are admin-managed and user-facing.

What users should experience:
- promoted content in the feed
- promoted content in search-related surfaces
- promoted content in category-driven discovery

What a placement is:
- a promoted listing or promoted category slot
- not an external ad link system

Rendering rule:
- the app should treat promoted items as native marketplace content
- clicking them should open internal listing/category experiences

Tracking:
- impressions and clicks are tracked through backend-supported promotion events

Implementation reference:
- `schema.yaml` promotions endpoints

## 11. Error Handling Rules

Global handling:
- `401`: clear tokens and move user to login if this is an authenticated flow
- `403`: show not-authorized state
- `404`: show not-found state
- `400`: show field or business-rule validation feedback
- `500`: show generic failure state and allow retry
- network failure: show offline/retry messaging

Payment-specific handling:
- invalid currency should be caught before checkout
- failed, pending, and cancelled must each get distinct UI
- no-refund messaging should be visible in cancellation and payment-related screens
- if provider verification disagrees with expectation, trust backend verification only

OTP-specific handling:
- always show generic OTP failure messaging
- allow retry or resend when cooldown/expiry rules permit

Implementation reference:
- `schema.yaml` response schemas and error statuses

## 12. Offline Behavior

This platform is online-first.

What can reasonably work offline if Flutter caches it:
- previously loaded listing cards and detail content
- previously loaded favorites UI state
- last known user session state until token use is required
- locally stored drafts or UI form input

What requires network:
- login and signup
- OTP request and verification
- live search and autocomplete
- live availability checks
- booking creation
- payment initiation and verification
- contact reveal
- notification sync
- guest-history conversion
- profile location updates

Important product rule:
- pricing, availability, booking status, payment status, and reveal state must always come from the backend when the user is making a real decision

## 13. Push Notifications

Customer-facing notifications should cover events like:
- account activation
- booking created
- booking confirmed
- booking cancelled
- payment successful
- payment failed
- saved listing deleted

Channel behavior:
- in-app notifications are first-class
- SMS and push are part of the product direction for phone-first communication
- email is supplementary only when the user has an email on file

Flutter should treat notifications as:
- a notification center experience
- a transport for transactional state changes
- a deep-link opportunity back into bookings, payments, and listing detail

Implementation reference:
- `schema.yaml` notifications endpoints

## 14. Notes For Flutter

Build the app around these product truths:
- phone is the main user identity
- guests are real supported users, not an afterthought
- payment verification, not checkout launch, controls success
- no refunds is a product rule, not just a backend detail
- verified and unverified listings can both appear, but the badge matters
- map and discovery features should use backend REST responses, not direct provider logic
- account conversion should feel like continuity, not a reset
