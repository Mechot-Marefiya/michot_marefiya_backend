# Mechot Marefiya Platform - Product Requirements Document (PRD)

**Version:** 2.0

**Status:** Codebase-aligned

**Source of truth:** `CODEBASE_MAP.md`, current backend modules, and current API contract in `schema.yaml`

**Last updated:** June 16, 2026

## 1. Overview

Mechot Marefiya is a multi-domain marketplace platform for the Ethiopian market. It supports discovery, booking, payment, contact-reveal, owner operations, company workspaces, and platform administration across hospitality, rentals, and sales use cases.

The platform currently supports:

- Hotels and room bookings
- Guest houses and room bookings
- Event space bookings
- Car rentals
- Car sales contact reveal
- Property rentals
- Property sales contact reveal

The backend is built with Django REST Framework and serves app and web clients through stable REST APIs. Payments are handled through Chapa. The platform uses Ethiopian Birr (ETB) as its primary business currency.

## 2. Product Surfaces

The current product is split across the following surfaces:

- Customer-facing client applications for browsing, booking, payment, favorites, notifications, and account management
- Company and owner-facing dashboards for listing management, bookings, payouts, and analytics
- Front desk and workspace operations for staff handling operational bookings and check-in style workflows
- Django admin and admin APIs for approvals, verification, monitoring, promotions, and platform controls

## 3. User Types

The current codebase supports these user and operator types:

### 3.1 Regular Users

Registered customers who browse listings, save favorites, make bookings, pay through Chapa, manage their history, and view payment or receipt information.

### 3.2 Guest Users

Unregistered users who can still interact with booking and reveal flows using phone-based verification. Guest activity is preserved and can later be attached to a registered account after verification.

### 3.3 Companies

Businesses that onboard to operate listings such as hotels, guest houses, car fleets, event spaces, and other managed inventory. Company users work through company-linked profiles and staff workspaces.

### 3.4 Front Desk / Workspace Staff

Operational staff assigned to a workspace. They can access domain-specific operational views, especially around bookings and hospitality workflows, without being platform admins.

### 3.5 Individual Owners

Private owners who can manage their own listings and bookings through an owner profile path. This is especially important for property rentals and sales-style connector flows.

### 3.6 Platform Admins

Platform-level operators who manage approvals, listing activation, verification, payment monitoring, disputes, promotions, templates, roles, and system-wide controls.

## 4. Authentication and Identity

The current platform is phone-first, but not OTP-only.

### 4.1 Current Authentication Model

- JWT authentication is the primary API auth mechanism
- Token issuance is available through `POST /api/v1/auth/token/`
- The current login payload is phone plus password
- Token refresh is available through `POST /api/v1/auth/token/refresh/`

### 4.2 OTP Flows

Phone verification is implemented through dedicated OTP endpoints:

- `POST /api/v1/auth/otp/request/`
- `POST /api/v1/auth/otp/verify/`

OTP is used in account and guest-linked verification flows, including some booking and contact-reveal journeys.

### 4.3 Guest Conversion

The platform preserves guest activity and supports converting guest-linked history into a registered account after verification. The current account API includes a dedicated guest-booking conversion flow.

### 4.4 Identity Controls

The user model and related services support phone verification state, phone change tracking, role-based behavior, and location-linked profile data.

## 5. Listing and Service Domains

The current product supports the following listing families:

### 5.1 Hotels

Hotels support room listings, availability, pricing, amenities, facilities, add-ons, booking flows, and booking snapshots.

### 5.2 Guest Houses

Guest houses support room inventory, availability, booking flows, and owner or company operations similar to hospitality inventory but under a dedicated guest-house domain.

### 5.3 Event Spaces

Event spaces support event-oriented listing, availability, and booking operations.

### 5.4 Car Rentals

Car rentals support availability, booking, operational requirements, and post-booking change flows. The current codebase includes:

- Driver and non-driver rental modes
- Optional pre-rental requirements
- `requires_code_3`
- `requires_business_license`
- reschedule and extension request support

### 5.5 Car Sales

Car sales are handled as connector flows. The buyer does not complete the sale on-platform. Instead, the platform monetizes contact reveal after payment and verification.

### 5.6 Property Rentals

Property rentals support direct booking-style flows, pricing previews, owner-side operations, and compliance-aware payment handling. This is now a real implemented booking domain, not just a planned concept.

### 5.7 Property Sales

Property sales are also handled as connector flows where payment is for contact reveal, not for the full sale transaction itself.

## 6. Discovery, Search, and Maps

The platform has active discovery and geospatial features.

### 6.1 Search and Feed

Implemented API capabilities include:

- listing feed
- structured search
- search suggestions
- nearby listing discovery
- within-bounds queries
- map pin responses

### 6.2 Maps Provider

The backend currently uses Geoapify-backed map and geocoding integrations rather than direct Google data calls. The API surface includes:

- `/api/v1/maps/autocomplete/`
- `/api/v1/maps/place-detail/`
- `/api/v1/maps/reverse-geocode/`

### 6.3 Listing Visibility in Discovery

A listing must be active to appear publicly. Verification is a separate trust signal and does not control visibility by itself.

## 7. Verification, Approval, and Visibility

The current codebase distinguishes clearly between activation and verification.

### 7.1 Activation

- Inactive listings are not publicly visible
- Admin review can activate a listing for public visibility

### 7.2 Verification

- Verification is a separate status and badge system
- Verified listings expose verification metadata such as verification timestamps and verifier attribution
- A listing may be active but still unverified
- Unverified status does not automatically hide the listing

This rule applies across listing families, including vehicles and property-style listings.

## 8. Booking Lifecycle

The codebase implements a multi-step booking lifecycle across its booking domains.

### 8.1 Core Booking Principles

- real availability checks
- pricing evaluation before booking
- booking reference generation
- pending-to-confirmed payment lifecycle
- immutable historical booking snapshots
- terms acceptance tracking

### 8.2 Supported Booking Domains

Implemented booking models and services exist for:

- hotel stays
- guest house stays
- event spaces
- car rentals
- property rentals

### 8.3 Guest Booking Support

Guest booking is supported through phone-based flows. The platform preserves the relationship between a guest identity and their booking history so it can later be converted.

### 8.4 Operational Booking Paths

The codebase also supports workspace and front-desk-oriented operational behavior, which is distinct from normal self-service customer booking.

## 9. Availability and Pricing

### 9.1 Availability

The current platform maintains availability models per listing family rather than using a single generic implementation. Availability is enforced through domain services for hospitality, events, cars, and property rentals.

### 9.2 Pricing

The pricing system currently supports:

- listing-level or inventory-level prices
- date-sensitive or seasonal pricing in relevant domains
- price previews in booking flows
- immutable recorded booking totals for historical accuracy

### 9.3 Add-ons and Related Commercial Data

Hospitality-style flows support add-ons and booking-side commercial extras where applicable.

### 9.4 Booking Window Controls

The current contract includes booking forward-window controls, including fields such as `booking_forward_window_days`.

## 10. Terms, Compliance, and Historical Records

The backend treats legal acceptance and historical snapshots as first-class data.

### 10.1 Terms Versioning

Terms and conditions are versioned and stored against booking or listing-related flows through dedicated models and services.

### 10.2 Immutable Booking History

The system preserves historical facts at booking time, including:

- booked pricing
- terms accepted
- related listing context
- guest versus registered-user path

### 10.3 Owner Compliance

Individual-owner compliance agreements are implemented in the codebase and are especially relevant for owner-operated property rental scenarios.

## 11. Payments and Financial Flows

Chapa is the active payment integration and all payment behavior is centralized in the payment app and service layer.

### 11.1 Supported Payment Operations

The current payment system supports:

- transaction initialization
- verification
- callback handling
- webhook handling
- cancellation handling
- owner ledger views
- receipt URL exposure
- dispute and transaction monitoring fields

### 11.2 Split and Payout Metadata

The codebase includes payout and split-related metadata, including owner-facing payout tracking and Chapa subaccount registration flows.

### 11.3 Tax Handling

Payment records now include tax-oriented fields such as tax amount, tax rate, and liability status. Property rental flows for individual owners are part of this compliance-aware model.

### 11.4 Refund Policy

The platform enforces a no-refund business rule in its current payment behavior and surrounding product messaging.

## 12. Contact-Reveal Connector Flows

Car sales and property sales are currently implemented as contact-reveal products rather than end-to-end sale settlement flows.

### 12.1 Flow Summary

1. A buyer views a sale listing.
2. The buyer initiates a contact reveal request.
3. The platform collects payment for the reveal.
4. After verification, the seller's contact information is revealed.
5. The actual sale happens off-platform.

### 12.2 Current Implementation Notes

The current backend includes dedicated models, serializers, and schemas for contact reveal across both car sales and property sales, including guest-capable OTP-backed paths.

## 13. Favorites and Saved State

Favorites are implemented for both authenticated users and guests.

The current behavior includes:

- generic favorites support
- snapshot-style saved listing behavior
- listing-specific favorite serialization

This allows saved-state behavior to survive later changes to live listing data.

## 14. Notifications

Notifications are a full application domain, not just ad hoc side effects.

### 14.1 Channels

The current notification system supports channel preferences and delivery metadata for:

- in-app notifications
- SMS-linked behavior
- email-linked behavior
- push-oriented delivery flags

### 14.2 Notification Features

The platform includes:

- persisted notification records
- user preferences
- reusable templates
- service-driven notification creation

## 15. Promotions and Merchandising

Promotions are now implemented as a first-class module.

### 15.1 Admin Promotion Control

The current product supports admin-managed promotional campaigns and placements.

### 15.2 Public Promotion Surface

The backend exposes public placement and tracking behavior so promoted inventory can be surfaced intentionally in customer-facing experiences.

## 16. Analytics and Reporting

Analytics are implemented for multiple operator personas.

### 16.1 Current Analytics Coverage

The backend includes analytics support for:

- company dashboards
- front desk and operational metrics
- admin-level overview metrics
- revenue and activity reporting

### 16.2 Processing Model

The current implementation mixes live queries and background or precomputed analytics support rather than relying on a purely one-mode design.

## 17. Roles and Access Patterns

The current role model in the codebase includes:

- `user`
- `admin`
- `company`
- `individual_owner`
- `front_desk`

Role and workspace information drive which operational surfaces a person sees and what data they can manage.

## 18. Platform Administration

Platform admins currently manage more than listing approval. Their responsibilities include:

- company and owner approval flows
- activation and verification decisions
- payment transaction monitoring
- disputes
- promotions
- roles and master data
- notification templates and operational controls

The Django admin remains part of the platform's real administrative surface alongside purpose-built APIs.

## 19. Background Processing and System Tasks

The codebase includes scheduled and background task behavior for operational continuity, including areas such as:

- OTP cleanup
- pending-booking auto-cancel behavior
- analytics cache or materialization work
- notification dispatch
- promotion synchronization
- geocoding-related tasks

## 20. Data Integrity Rules

The platform follows a historical-integrity model where past commercial facts are preserved. The current implementation is designed so that later listing edits do not rewrite the historical context of completed booking or payment records.

Examples include preserving:

- booking totals at the time of booking
- terms acceptance state
- payment records and receipt references
- listing snapshots and related saved-state data

## 21. Current Non-Goals and Boundaries

The current backend does not act as a full on-platform broker for car sales or property sales. Those remain connector flows.

The Django admin remains the platform-admin tool rather than being fully replaced by a customer-facing React or Flutter surface.

Any future PRD updates should continue to treat the codebase and API contract as authoritative, especially for:

- auth payloads
- role names
- endpoint paths
- booking lifecycle behavior
- payment semantics
- activation versus verification rules

## 22. Platform Summary

| Capability | Current State |
| --- | --- |
| Primary backend | Django REST Framework modular monolith |
| Primary auth | JWT with phone-plus-password login, plus OTP verification flows |
| Primary payment gateway | Chapa |
| Primary currency | ETB |
| Booking domains | Hotels, guest houses, event spaces, car rentals, property rentals |
| Connector domains | Car sales, property sales |
| Favorites | Supported for users and guests |
| Promotions | Implemented |
| Notifications | Implemented with preferences and templates |
| Analytics | Implemented for company, front desk, and admin contexts |
| Listing trust model | Activation controls visibility; verification adds trust metadata |
| Compliance support | Terms versioning, owner agreements, tax-aware payment fields |
| Distinctive platform value | Unified Ethiopian marketplace across booking, rentals, and connector sales with owner, company, and operational workflows in one system |
