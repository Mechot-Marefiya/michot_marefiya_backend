# React App Workflow
# User types: Regular, Company Roles, Individual Owners
# Last updated: 2026-06-16

## 1. App Overview

Mechot Marefiya is a multi-domain marketplace for the Ethiopian market. The product combines discovery, booking, payment, owner operations, and contact-reveal flows across:

- hotels
- guest houses
- event spaces
- car rentals
- property rentals
- car sales contact reveal
- property sales contact reveal

The React app is the web surface for:

- regular users who browse, book, and pay
- company-side users who manage listings, bookings, operations, and analytics
- individual owners who manage their own listings, bookings, and payment visibility

The React app does not replace:

- Django admin or Jazzmin for platform administration
- the Flutter customer app
- backend-only jobs such as payment verification, OTP dispatch, analytics materialization, or geocoding

Recommended navigation model:

- public shell: home, search, categories, map, listing detail, login, register
- regular user shell: bookings, payments, favorites, profile, notifications
- company shell: workspace dashboard, listings, bookings, availability, pricing, analytics, staff
- owner shell: listings, bookings, payouts, agreement status, promotions visibility, profile

Companion docs:

- use `REACT_QUICKSTART.md` for setup and environment
- use `schema.yaml` for the live contract
- use `REACT_API_GUIDE.md` for endpoint wiring

## 2. Authentication Flows

### 2a. Registration

Regular user registration is phone-first.

Expected flow:
1. User enters phone, password, and confirmation.
2. React submits registration.
3. React sends the user through OTP verification.
4. After OTP success, the account becomes usable and React can continue to login or authenticated state.

Business rules:

- phone is the primary identity
- email is optional, not the core login identifier
- duplicate phone numbers are blocked
- guest history linked to the same phone can later be attached to the registered account
- phone change abuse controls exist in the backend and React should surface their validation messages clearly

Company staff account creation is not a public self-registration flow for every staff member.

Current product model:

- company profiles can onboard through the company path
- staff accounts are created by the company owner or platform-controlled operations flow
- React should treat staff creation as a managed workflow, not as an open signup screen

Individual owner onboarding is also managed.

Current product model:

- owner records and agreement state are controlled through platform workflows
- React should not assume a fully self-service owner signup
- owners should be guided into a provisioned-account or admin-assisted onboarding flow

OTP verification is part of the trust model for:

- account verification
- guest-sensitive flows
- some booking and contact-reveal paths

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 1 for auth
- see `REACT_API_GUIDE.md` Section 1 for OTP

### 2b. Login

All user types use the same authentication entry point. React should present one login form and route after identity is known.

Current login model:

- phone plus password is the stable login path
- OTP is a supporting verification flow, not a separate product universe

After login:
1. store tokens securely
2. load current profile
3. read role and workspace context
4. route to the correct dashboard

Dashboard routing should be based on backend truth:

- `user` -> regular user experience
- `company` -> company management dashboard
- `front_desk` -> workspace operations dashboard
- `individual_owner` -> owner dashboard
- `admin` -> out of scope for this React app unless an explicit admin surface is later added

Important rule:

- React should not infer role from email, route name, or listing ownership guesses
- always trust the authenticated profile payload

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 1

### 2c. Session management

React should treat JWT refresh as part of normal session continuity.

Rules:

- refresh access tokens before or when they expire
- if refresh fails, clear tokens and redirect to login
- on `401`, do not keep the app in a broken half-authenticated state
- if a remember-me option is added, it must only affect client persistence strategy, not backend token semantics

Recommended behavior:

- keep refresh handling centralized in the API client layer
- clear user-scoped caches on logout or refresh failure
- preserve public browsing state when possible even after auth loss

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 1

## 3. Regular User Flows

### 3a. Browse and discover listings

The regular-user home experience is a discovery product first.

What the user can do:

- browse a mixed home feed
- search by keyword or place intent
- filter by listing type
- switch between list and map views
- open promoted placements
- save favorites

Feed behavior:

- if location is available, the experience can become proximity-aware
- if location is not available, the feed still works with default discovery ordering
- React should support listing-type filters for all current families, including event spaces, car rentals, and property sales

Location permission on web:

- ask only when the user is entering a map or nearby-oriented flow
- explain the benefit clearly
- degrade gracefully when permission is denied

Search behavior:

- keyword and place-driven search should feel unified
- radius filters matter most when coordinates are known
- map pins should come from backend discovery responses, not client-side geospatial math

Business rules:

- only active listings should appear publicly
- unverified listings may still be visible
- verification is a trust badge, not a visibility gate
- listings may not always have coordinates yet because geocoding can complete asynchronously after save

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 3 for discovery and search
- see `REACT_API_GUIDE.md` Section 6 for maps and proximity

### 3b. Listing detail page

Every listing detail page should help the user answer three questions fast:

1. what is this
2. can I trust it
3. what is the next action

Common detail content:

- title and media
- formatted address
- map preview when coordinates exist
- verification badge
- availability context
- pricing context
- category-specific details
- favorite state
- the primary CTA

Listing-type expectations:

- hotel and guest house: room options, amenities, facilities, booking CTA
- property rental: stay terms, price preview context, booking CTA
- car rental: rental mode and requirement visibility, booking CTA
- car sale and property sale: seller context summary without revealing contact until payment unlocks it
- event space: capacity and event-oriented booking CTA

Verification display:

- show a verified badge when `is_verified` is true
- if verification note is present in the payload and the design supports it, show it as supporting trust context

Map behavior:

- render a pin when coordinates exist
- if coordinates are missing, still show the address cleanly instead of breaking layout

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 3 for listing details

### 3c. Booking flow (per listing type)

The booking UX should make the commercial rules obvious before the user reaches payment.

Hotel booking:
1. choose room and dates
2. review availability
3. preview pricing
4. select add-ons if offered
5. accept terms
6. create the booking in pending state
7. continue to payment

Guesthouse booking:
1. choose room and dates
2. review availability and occupancy fit
3. preview pricing
4. accept terms
5. create pending booking
6. continue to payment

Property rental booking:
1. choose dates
2. review booking window eligibility
3. preview totals
4. accept terms
5. create pending booking
6. continue to payment

Business rules React must respect:

- forward booking windows are enforced by the backend through listing-level controls such as `booking_forward_window_days`
- the UI should prevent obviously invalid dates when the restriction is known
- the backend is still the final authority on allowed dates
- terms acceptance is mandatory before booking creation
- bookings start as pending and become truly paid only after payment verification
- no-refund messaging should be visible around cancellation-sensitive flows

Guest-sensitive flows:

- some guest booking journeys require OTP verification before lookup or protected access
- React should treat guest verification as part of the booking journey, not as a separate account requirement

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 4 for hotels, guest houses, property rentals, event spaces, and car rentals
- see `REACT_API_GUIDE.md` Section 12 for payment handoff

### 3d. Contact reveal flow

Car sales and property sales use a connector model, not a full on-platform sale settlement.

What the user is paying for:

- access to the seller's contact details
- not the sale price of the asset itself

Flow:
1. user opens a car-sale or property-sale listing
2. user requests contact reveal
3. if guest verification is required, React completes that checkpoint
4. payment is initiated
5. after verified payment, contact becomes available
6. the actual sale continues off-platform

State model React should understand:

- `requested`: reveal request exists but access is not unlocked
- `paid`: payment completed or verified
- `revealed`: contact is now available to the buyer

UX rules:

- never show seller phone or email before unlock
- treat payment success and contact reveal as related but not identical states
- if verification is still pending, show a processing state instead of assuming failure

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 5 for car sales and property sales
- see `REACT_API_GUIDE.md` Section 1 for guest OTP if needed

### 3e. My bookings

Regular users need a clean history view across supported booking domains.

The bookings area should support:

- list view
- detail view
- status visibility
- cancellation where allowed
- booking reference visibility
- receipt visibility when a payment exists

Cancellation UX:

- React should not promise refunds
- show whatever cancellation outcome the backend returns
- if a booking is cancelable, make the action explicit and confirm before sending it
- if a booking is no longer cancelable, explain why instead of hiding the booking

Receipt UX:

- if a transaction includes `receipt_url`, render a clear receipt action
- if no receipt exists yet, show the booking state without inventing one

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 4 for booking history and protected booking actions
- see `REACT_API_GUIDE.md` Section 12 for payment verification and receipts

### 3f. Payment history

The payments area is the user's commercial audit trail.

It should show:

- transaction status
- amount
- currency
- related booking or reveal context
- receipt availability
- tax breakdown when returned by the backend

Property-rental tax handling:

- React should surface tax fields when present
- do not hide tax just because it is only relevant to certain booking types

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 12

## 4. Company Role Flows

Important modeling note:

- the backend does not expose separate auth role codes for hotel staff, guesthouse staff, property manager, and car sales agent
- in practice these are workspace-specific dashboard modes driven by `company` or `front_desk` access plus workspace assignment

### 4a. Hotel Staff Dashboard

Hotel-side users are responsible for operational control of their own hospitality inventory.

Typical responsibilities:

- review hotel and room details
- manage incoming bookings
- inspect guest details for operational needs
- manage availability
- manage pricing-related configuration if their permissions allow it
- use workspace booking views where relevant

Listing creation rule:

- React should not assume every hotel staff account can create listings
- creation and editing controls should follow what the backend allows for the current user
- if a write action returns `403`, show a permission message rather than treating it as a broken screen

Booking window rule:

- if the dashboard exposes forward-booking controls, treat them as business configuration, not as a cosmetic setting

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 7 for company hospitality operations

### 4b. Guesthouse Staff Dashboard

Guesthouse staff follow the same general pattern as hotel operations, but with guesthouse-specific inventory and booking models.

Main differences:

- guesthouse rooms and inventories are managed in their own domain
- the UI should use guesthouse language and room structures rather than copying hotel wording blindly

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 7

### 4c. Property Manager Dashboard

Property-management users handle property-rental inventory and booking operations.

Key responsibilities:

- manage property rental listings
- monitor booking activity
- manage listing availability and active state
- review payment and tax-aware totals for bookings

Compliance note:

- individual-owner compliance agreements are a real product concept, but they are most important on the owner path
- if company-managed property inventory surfaces agreement data, show it read-only
- React should not invent a self-service compliance signing flow for company users

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 7

### 4d. Car Sales Agent Dashboard

Car-sales operators manage sale listings and the reveal funnel.

Key responsibilities:

- manage car-sale listings
- view contact reveal requests
- review payment status for each reveal
- understand whether the buyer has unlocked contact access

Important rule:

- the dashboard manages listing and reveal visibility, not the off-platform sale transaction itself

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 7

### 4e. Shared company role behaviors

All company-side experiences share the same guardrails:

- users only see their own company or workspace data
- they should not see another company's listings, bookings, or transactions
- backend permissions are authoritative
- React should render empty states and permission states cleanly
- `403` means permission denied, not application failure

Analytics behavior:

- company analytics and front-desk analytics are separate surfaces
- only show dashboards that match the authenticated role and workspace context

## 5. Individual Owner Flows

### 5a. Owner registration and onboarding

Individual owners are not a pure open-signup consumer flow.

React should treat onboarding as:

- account provisioned or enabled through platform workflow
- owner logs in after setup
- owner sees current agreement and profile state immediately

Compliance agreement behavior:

- show agreement status clearly
- if unsigned or inactive, prompt the owner to contact platform operations
- do not offer self-service agreement signing in the owner UI

Verification behavior:

- owners should be able to see listing verification state
- verification remains an admin-controlled trust signal

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 10

### 5b. Listing management

Owners should be able to manage the listings they are responsible for without needing Django admin.

Typical actions:

- create listing
- edit listing
- toggle listing state where permitted
- upload and manage images
- review verification and active status

Address and map workflow:

1. owner types an address into an autocomplete field
2. React requests suggestion data from the backend map helper flow
3. owner selects a suggestion
4. React requests place detail from the backend helper flow
5. React shows a map preview and resolved address
6. form is submitted with the place identifier and resolved location data

Important correction:

- the backend map provider is Geoapify-backed today
- React should not call Google directly for listing address resolution

Async geocoding rule:

- some coordinates can be enriched after save
- a listing may save successfully before final coordinates are visible everywhere

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 6 for maps helpers
- see `REACT_API_GUIDE.md` Section 8 for owner listing management

### 5c. Booking management

Owners need operational visibility into bookings that affect their listings.

The owner dashboard should support:

- booking list
- booking detail
- booking status visibility
- guest detail visibility where the backend allows it
- cancellation or follow-up actions only where authorized

React should group bookings by listing domain clearly instead of forcing a single confusing mixed table.

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 8 for owner-side listing context
- see `REACT_API_GUIDE.md` Section 9 for owner financial booking-linked data

### 5d. Financial overview

Owners need a simple financial picture, not raw payment internals.

The UI should emphasize:

- payout-oriented transaction history
- booking-linked earnings context
- tax-aware totals for property-rental cases
- receipt or transaction references where available

Important accuracy rule:

- the current backend exposes tax and receipt fields on transactions
- React should use the fields the backend actually returns
- do not invent a standalone tax-ledger experience unless a dedicated endpoint is later added

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 9

### 5e. Promotions

Promotions are currently admin-managed.

Owner experience should focus on:

- seeing whether a listing appears in promoted placements
- understanding that campaign creation and placement control are not self-serve owner features in the current product

If a future self-serve promotion request flow is added, it should be treated as a new product capability, not assumed now.

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 11

## 6. Map Integration on React

### 6a. Listing cards with map context

Listing cards should be map-aware but resilient.

Rules:

- show `formatted_address` when available
- show distance when the backend returns `distance_km`
- render pins only for listings with coordinates
- if coordinates are missing, keep the card useful with address and category information

### 6b. Listing registration address input

Authenticated listing-management flows should use a backend-backed autocomplete component.

Rules:

- autocomplete suggestions come from the backend helper flow
- place details also come from the backend helper flow
- React should show a preview pin before save when possible
- React should submit the location metadata the backend expects instead of trying to reverse-engineer it client-side

### 6c. Proximity search on web

Map and nearby discovery should feel intentional.

Recommended flow:

1. ask for location permission when the user enters a nearby or map search journey
2. if permission is granted, persist user location for better future discovery
3. show `distance_km` in result cards when returned
4. reload results when the user pans or changes bounds

Product rules:

- proximity is backend-calculated
- authenticated location persistence is account-scoped
- guest browsing should still work without saved location

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 6

## 7. Payment Flow (Chapa on React)

### 7a. Standard payment

React does not own payment verification. It owns the user journey into and out of payment.

Expected flow:
1. user confirms a payable action
2. backend creates a pending transaction and returns payment data
3. React redirects to the hosted Chapa checkout by default
4. user returns from Chapa
5. React refreshes state and checks verified backend payment status
6. UI shows success, pending, or failure state

Important rule:

- do not trust redirect alone as proof of success
- final product state should be driven by backend verification

Inline checkout:

- only use inline or HTML checkout if the product explicitly chooses that integration style
- the hosted redirect path is simpler and matches the current backend model well

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 12

### 7b. Split payment awareness

React does not calculate settlement, but it must show the commercial breakdown clearly when the backend provides it.

Show what the backend returns, especially:

- grand total
- tax amount
- tax rate
- owner or platform split-related amounts if included in the payload

Important rule:

- do not recompute split or tax logic in the browser
- render the backend's authoritative breakdown

### 7c. Payment statuses per transaction

Recommended React treatment:

- `pending`: payment started but not yet verified; show processing or waiting state
- `success`: payment verified; unlock the related booking or reveal result
- `failed`: payment did not complete; allow retry if the flow supports it
- `cancelled`: payment link or transaction was cancelled; show closed state
- `refunded`: show post-payment exception state and direct the user to support if needed
- `reversed`: show that the transaction was reversed and that the original paid action may no longer be valid

Business rule:

- the platform currently operates under a no-refund policy, so refunded or reversed states are exception handling states, not normal user options

## 8. Admin Verification Surface (React only)

In the main React app, verification is primarily a read-only trust surface.

React should:

- show verified badges on listing cards and details
- show verification timestamps or notes only when helpful
- never imply that regular users, owners, or company staff can self-verify listings

Current product boundary:

- platform admin workflows remain outside this React app by default
- Django admin and admin-specific backend surfaces remain the operational source for verification actions

## 9. Promotional Placements

Promotions are first-class content blocks, not random ads.

React should render promoted listing cards in:

- home feed
- search results
- category pages

Render behavior:

- trust backend placement selection
- place promoted cards according to slot type
- keep promotion visuals clearly distinct but still native to the product UI

Tracking behavior:

- click or impression tracking should be treated as a backend analytics event, not as a client-only metric

When endpoint wiring is needed:
- see `REACT_API_GUIDE.md` Section 11

## 10. Error Handling Rules

React should treat backend responses as product states, not just transport failures.

- `401`: clear tokens and redirect to login
- `403`: show permission denied and keep the app stable
- `404`: show not found experience
- `400`: show field errors inline and preserve user input where possible
- `500`: show a generic failure state without exposing internals
- network failure: show an offline or retry banner

Additional rules:

- never crash the dashboard on permission errors
- keep read-only public pages resilient even if a related authenticated widget fails
- surface backend validation exactly where the user can act on it

## 11. Business Rules Summary

- phone is the primary identity across registration, verification, and guest trust flows
- booking windows are limited by backend-configured forward-booking rules such as `booking_forward_window_days`
- property-rental transactions can include tax-aware breakdowns
- contact reveal is always payment-gated
- owner compliance agreement status is read-only in the client and operationally managed by the platform
- listing verification is admin-controlled
- listing activation controls public visibility; verification does not
- payment success must be backend-verified before React unlocks value
- unverified listings can still be visible if active
- guest and registered flows must both respect OTP checkpoints where required
