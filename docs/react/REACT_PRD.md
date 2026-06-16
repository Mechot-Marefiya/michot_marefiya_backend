# React Product Requirements Document
# Platform: Michot Marefiya
# Scope: React web app only
# Last updated: 2026-06-16

This document is a React-focused subset of [PRD.md](/c:/Users/Surafel/Documents/Project%20Works/Mechot%20IT/Mechot%20Marefiya/Project/michot_marefiya_backend/PRD.md:1).

It keeps the product behavior, user flows, and frontend-facing business rules that matter to the React app, while leaving out backend implementation detail such as Celery tasks, Redis behavior, database structure, and internal service architecture.

Companion docs:

- [REACT_QUICKSTART.md](/c:/Users/Surafel/Documents/Project%20Works/Mechot%20IT/Mechot%20Marefiya/Project/michot_marefiya_backend/docs/react/REACT_QUICKSTART.md:1) for setup and environment
- [REACT_WORKFLOW.md](/c:/Users/Surafel/Documents/Project%20Works/Mechot%20IT/Mechot%20Marefiya/Project/michot_marefiya_backend/docs/react/REACT_WORKFLOW.md:1) for end-to-end user journeys
- [REACT_API_GUIDE.md](/c:/Users/Surafel/Documents/Project%20Works/Mechot%20IT/Mechot%20Marefiya/Project/michot_marefiya_backend/docs/react/REACT_API_GUIDE.md:1) for endpoint contracts

## 1. Product Summary

Mechot Marefiya is a multi-domain Ethiopian marketplace that combines discovery, booking, payments, owner operations, and paid contact-reveal flows in one product.

The React app covers:

- public browsing and search
- account login and profile management
- regular-user booking and payment flows
- company-side listing and operations dashboards
- individual-owner listing, compliance, and financial views
- promoted placement rendering

The React app does not replace:

- Django admin or Jazzmin for platform administration
- the Flutter mobile customer app
- internal-only platform operations such as payment verification processing, notification dispatch, or analytics jobs

## 2. Product Domains

The React app must support these product families:

- hotels
- guest houses
- event spaces
- car rentals
- property rentals
- car sales contact reveal
- property sales contact reveal

These families do not all behave the same.

Booking-style families:

- hotels
- guest houses
- event spaces
- car rentals
- property rentals

Connector-style families:

- car sales
- property sales

For connector-style families, the user pays to reveal seller contact details, not to complete the full sale on-platform.

## 3. User Types

The React product must be designed for three main groups.

### 3.1 Regular Users

Regular users browse listings, save favorites, book services, make payments, manage their booking history, and view receipts or payment states.

They may be:

- authenticated registered users
- guests moving through phone-verified guest flows where supported

### 3.2 Company Roles

Company-side users manage operational inventory and bookings for their own workspace or domain.

In product terms, this can look like:

- hotel staff
- guesthouse staff
- property-management staff
- car-side operators
- front-desk or workspace operators

Important frontend rule:

- the backend role model is centered on `company` and `front_desk`
- the React UI should treat many company experiences as workspace-specific dashboard modes, not as totally separate auth systems

### 3.3 Individual Owners

Individual owners manage their own listings, track bookings, review payout-related financial data, and see compliance agreement status.

Owner onboarding is operationally managed by the platform. The React app should treat owner access as a provisioned product path, not a fully open public signup flow.

## 4. Authentication and Identity

The React app is built around a phone-first identity model.

Core product rules:

- phone is the primary identity
- email is optional
- JWT is the authenticated API session mechanism
- OTP is part of account trust and guest-sensitive actions

Frontend implications:

- use phone as the main login and verification identifier
- support OTP request and verify flows cleanly
- preserve public browsing even when auth expires
- route dashboards based on the authenticated profile and workspace context

## 5. Public Discovery Experience

Discovery is one of the main jobs of the React app.

The public web experience should support:

- home feed
- category browsing
- search
- search suggestions
- nearby discovery
- map browsing
- promoted placements

Core discovery rules:

- only active listings should appear publicly
- unverified listings may still be visible
- verification is a trust signal, not a visibility switch
- some listings may temporarily have no coordinates yet, so the UI must degrade gracefully

Listing cards should emphasize:

- title
- price context
- address
- trust state
- listing type
- next action

## 6. Maps and Location

The React app should support a map-aware product experience, but the backend remains the source of truth for map data and place resolution.

Frontend-facing rules:

- render pins from backend coordinates
- show distance when the backend returns it
- support nearby and within-bounds exploration
- use backend place helper flows for authenticated listing-management address input

Important product note:

- the active backend provider is Geoapify-backed
- React should not depend on Google-specific backend behavior

## 7. Listing Detail Experience

Every listing detail page should answer:

1. what the listing is
2. whether the listing appears trustworthy
3. what the user can do next

Common detail content:

- media
- title
- description
- formatted address
- map preview where coordinates exist
- verification badge
- category-specific metadata
- pricing context
- CTA

Category-specific CTA behavior:

- booking CTA for booking-style products
- contact-reveal CTA for car sales and property sales

## 8. Booking Experience

The React app must support booking-style flows for:

- hotels
- guest houses
- event spaces
- car rentals
- property rentals

Shared booking rules:

- users should see price preview before committing
- terms acceptance is required before booking creation
- booking dates may be restricted by `booking_forward_window_days`
- bookings begin in a pending state
- payment verification is required before the UI treats a booking as fully paid or unlocked

Guest-sensitive rules:

- some guest flows require OTP verification before protected guest actions
- guest verification should feel like part of the booking journey, not like forced account creation

## 9. Contact-Reveal Experience

Car sales and property sales follow a connector model.

The user journey is:

1. browse sale listing
2. request contact reveal
3. complete any required guest verification
4. initiate payment
5. after verified payment, unlock seller contact
6. continue the actual sale off-platform

Frontend rules:

- never reveal seller contact before unlock
- represent the reveal state clearly
- handle pending verification without falsely showing failure

## 10. Payment Experience

The React app owns the user-facing payment journey, but not the underlying payment verification logic.

What React should do:

- initiate payment through the backend
- redirect to hosted Chapa checkout by default
- support success, pending, and failure return states
- refresh transaction state after return
- show receipts when available

Core payment rules:

- do not trust the redirect alone as proof of payment success
- use backend verification state
- no-refund messaging should be reflected where cancellation or payment outcomes matter
- render backend-provided commercial breakdowns instead of recalculating them in the browser

Important breakdown fields for the UI:

- service fee
- owner price
- tax amount
- tax rate
- grand total
- receipt URL

## 11. Company Dashboard Scope

The company-side React experience should provide operational dashboards without exposing other companies' data.

Typical company capabilities:

- view and edit owned listing data where allowed
- manage availability
- review bookings
- use workspace booking views
- inspect operational booking details
- access company or front-desk dashboards relevant to the authenticated workspace

Frontend rules:

- permissions are backend-controlled
- `403` means show a stable permission-denied state
- UI should reflect workspace context rather than pretending every staff user has universal company access

## 12. Individual Owner Dashboard Scope

The owner-side React experience should let owners manage their part of the marketplace without needing admin tools.

Typical owner capabilities:

- create and edit owned listings
- manage listing media and address data
- see booking activity tied to owned listings
- review payout-oriented transaction history
- view tax-aware totals for relevant property-rental cases
- review agreement status

Important owner rules:

- agreement status is visible but not self-managed through the owner UI
- owners see verification status, but cannot self-verify
- promotions are visible as outcomes, not self-serve campaign controls in the current product

## 13. Promotions

Promotions are first-class merchandising blocks in the React experience.

The React app should:

- render promoted placements in the feed, search, and category contexts
- follow backend slot ordering
- track placement interactions through the backend

Promotions should feel native to the product and clearly intentional, not like generic ad clutter.

## 14. Verification and Trust

Verification is a trust feature that React must display consistently.

Listing trust signals exposed to the UI include:

- verified status
- verification timestamp
- verifier reference
- optional verification note

Important product rule:

- verification is not the same as activation
- a listing can be visible and still be unverified

## 15. Favorites, History, and Continuity

The product should feel continuous across anonymous and authenticated usage.

React should support:

- favorites
- booking history
- payment history
- guest-to-user continuity where the backend supports linking

The goal is that users do not feel like they lose product context just because they started as a guest or later registered.

## 16. Error Handling Expectations

React should treat backend responses as product states, not just technical failures.

Expected behavior:

- `400`: show actionable inline errors
- `401`: clear session and redirect to login when appropriate
- `403`: show permission denied without crashing
- `404`: show a not-found experience
- network failure: show retry or offline states

Important UI principle:

- public browsing and authenticated dashboard widgets should fail independently where possible
- one broken panel should not collapse the entire screen

## 17. Business Rules React Must Reflect

- phone is the primary identity
- bookings are constrained by forward-booking windows when configured
- payment completion is backend-verified, not redirect-verified
- contact reveal is always payment-gated
- property-rental flows can include tax-aware commercial breakdowns
- verification is admin-controlled
- visibility depends on activation, not verification alone
- guest and registered flows must both respect OTP checkpoints where required
- owner agreement status is operationally managed and read-only in the frontend

## 18. React Success Criteria

The React product is successful when it:

- makes public discovery fast and trustworthy
- makes booking and payment flows clear and low-friction
- handles contact reveal safely and understandably
- gives company users usable operational dashboards
- gives owners clear visibility into listings, compliance, and money
- respects backend permissions and business rules without confusing the user
