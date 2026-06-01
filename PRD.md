**Mechot Marefiya Platform — Product Requirements Document (PRD)**

**Version:** 1.0

**Status:** Final Draft

**Prepared by:** Backend Developer (from presentation + stakeholder comments)

**1\. Overview**

Mechot Marefiya is a comprehensive digital marketplace platform built specifically for the Ethiopian market. It consolidates hotel bookings, guesthouse rentals, event space bookings, car rentals, car sales, and house/property sales and rentals into a single platform. All transactions are in Ethiopian Birr (ETB), powered by Chapa as the payment gateway, and delivered primarily through a Flutter mobile application.

The platform's core uniqueness is enabling regular private individuals to rent or sell their own property (house, car, room) through the platform — with the platform acting as a licensed intermediary to handle tax and regulatory compliance on their behalf.

**2\. User Types**

The platform has four distinct user types:

**2.1 Customers (Registered Users)** Users who download the app or visit the website to book or purchase services. Registration is phone-based. Email is optional and used for supplementary notifications. All verification (OTP, identity checks) happens via phone.

**2.2 Guest Users** Users who book or order without creating an account. They provide only a phone number. Guests can place bookings with the same functionality as registered users for their first interaction. The system must support converting a guest to a registered user, carrying over their full booking history.

**2.3 Companies** Businesses that register on the platform to list hotels, guesthouses, event spaces, car fleets, cars for sale, or houses for sale/rent. They self-register via the app and go through an admin approval process before their listings go live.

**2.4 Individual Owners** Private individuals who want to list their personal property (house, car, room) for rent or sale. Individual owners do NOT self-register. They are verified in person by the platform admin, who then creates their profile and staff account manually on the system. This is a deliberate trust and compliance design decision.

**2.5 Platform Admin** Manages the entire platform — approves companies and individual owner profiles, verifies listings, monitors transactions, manages master data (facility types, amenity types, notification templates, roles), runs promotional configurations, and resolves disputes.

**3\. Authentication & Identity**

- **Primary login method:** Phone number (OTP-based).
- **Email:** Optional. Can be set up after registration but is not required for any core function.
- **All verifications** (account activation, booking confirmations, password changes) use phone-based OTP.
- Guest users interact using phone only, with no account required.

**4\. Listings & Services**

**4.1 Hotel Rooms**

Full hotel experience: room types, amenities, facilities, seasonal pricing, add-ons (breakfast, airport shuttle, extra bed, etc.), terms and conditions, and availability calendar.

**4.2 Guesthouses**

Smaller privately run accommodations. Same structure as hotels but typically with fewer room types and simpler setup. Managed identically through the listing system.

**4.3 Event Spaces**

Conference halls, auditoriums, meeting rooms. Bookable by the day for corporate or social events.

**4.4 Car Rentals**

Individual cars or fleets available for daily rental. Managed per unit. Supports both company-owned fleets and privately owned individual cars.

**Car Rental rules:**

- Renting with a driver and without a driver are treated as distinct rental types with different requirements.
- Without-driver rentals require additional documentation from the renter (driver's license, cheque guarantee, etc.). The full detail of this documentation workflow is on hold pending further specification.
- Cars with code-3 plate numbers can only be rented when the renter provides a valid Business License. Other car types cannot be rented
- Car owners may optionally require the renter to fill out a form before completing the rental. This form is customizable by the owner.
- The rental booking must include a date-changing feature — renters should be able to adjust rental dates if the date they change to is not taken for that booking item.
- Before a car rental listing goes live, it should be reviewed. If verified by admin, a "Verified" tag is shown. If not yet verified, the listing shows "Not Verified." But still visible so both are visible but tagged appropriately.

**4.5 Car Sales**

Cars can be sold, not just rented. The platform acts as a connector (not a broker). When a client is interested in purchasing a car, they request the seller's contact details. After paying a contact-reveal fee, the platform provides the seller's contact and the transaction continues off-platform between the two parties.

Any type of car can be listed for sale.

**4.6 House/Property Rentals**

Regular individuals can rent out their house, apartment, or rooms. The platform acts as a licensed intermediary — since private individuals do not have a rental license, the platform handles tax obligations and regulatory compliance on their behalf.

Pricing flow for unlicensed individual house rentals:

- Owner sets their desired price (e.g., 3,000 ETB/month).
- Platform adds its service charge on top.
- Platform adds 15% tax (to remit to the government).
- The client-facing price reflects all three components.
- The individual owner has a formal agreement with the platform for this arrangement.

**4.7 House/Property Sales**

Houses and any kind of property can be sold through the platform. Same connector model as car sales: the platform connects buyer and seller, the buyer pays to reveal the seller's contact details, and the actual transaction happens between the parties directly.

**5\. Listing Verification**

- Every listing (hotel, car, guesthouse, event space, house) submitted by a company or individual must go through admin verification before or after going live.
- If verified: a "Verified by Mechot" badge is shown on the listing.
- If not yet verified: a "Not Verified" label is shown.
- The admin records the date of verification for each listing.
- This system applies to all listing types, including car rentals (see 4.4).
- It won’t affect the visibility but tag should be shown.

**6\. Booking System**

**6.1 Booking Flow (General)**

1.  User selects a listing and dates.
2.  System checks real-time availability for every day in the requested period.
3.  System calculates the correct price per day (accounting for seasonal pricing, weekend rates, and multipliers).
4.  User selects add-ons if applicable.
5.  Full cost breakdown displayed.
6.  Terms & Conditions presented. User must agree before proceeding.
7.  System permanently records: which T&C version was agreed to, the exact timestamp, and a full copy of the T&C text at that moment.
8.  Booking created with status: PENDING.
9.  Unique booking reference generated (e.g., H-X7Y2Z9 for hotels, C-AB3DE4 for cars).
10. User proceeds to payment.

**6.2 Service Charge on First Booking**

Every client's first booking on the platform is free of service charge. This applies to phone numbers so each phone number will get one service fee free booking whether the client is a guest or a registered user each phone number will get one free service fee free service.

For registered user we will only allow 3 phone number changes and a week ban before changing another that way we will control abuse of this feature.

**6.3 Service Charge Scope**

The platform service charge is applied only to the core booking amount. It does NOT apply to add-ons. For example: if a customer books a hotel room and adds breakfast and dinner, the service fee is calculated only on the room booking price, not on the add-on prices.

**6.4 Walk-In Customers**

Receptionists can create bookings manually via the staff dashboard for walk-in guests. Walk-in bookings are tagged with status WALK-IN. No service charge is applied to the platform for walk-in bookings — this is a direct hotel-to-guest transaction that does not go through the platform payment split.

**6.5 Guest Checkout**

Guests can complete bookings without an account using only their phone number. The system records the booking tied to the phone number. Guest history must be preserved and associated with the phone number so that it can be transferred when the guest converts to a registered user. An OTP will be sent on bookings to confirm if the user is indeed a legit and also user booking using there own number.

**6.6 Booking Date Restriction**

To protect against pricing volatility (since prices can change frequently), the platform admin can set a check-in date restriction window. For example: admin sets a 5-day forward restriction. If today is June 1, a customer cannot set a check-in date beyond June 6. This restriction is configurable by the listing owner and applies per-listing category as designed. Default will be 5 days.

**6.7 No Refunds**

No refund is available for any service payment on the platform. This is a firm business rule. It must be clearly communicated in T&C and on payment confirmation screens.

**7\. Pricing System**

**7.1 Seasonal Pricing**

Listing owners (hotels, guesthouses, car owners) can define seasonal pricing rules:

- Season name (e.g., "Ethiopian Christmas - Genna")
- Date range or specific recurring days (e.g., "Every Friday and Saturday")
- Multiplier (e.g., 1.5 for 50% increase, 0.8 for 20% discount)
- Priority level (when multiple rules overlap on the same date, the higher priority rule wins)

**7.2 Add-On Pricing**

Add-ons are priced separately from the base booking. Service charges are not applied to add-on amounts.

**7.3 Historical Price Preservation**

The price at the time of booking is permanently recorded. If the owner later changes the price, existing bookings are not affected.

**8\. Payment System (Chapa Integration)**

**8.1 Payment Gateway**

Chapa is the exclusive payment gateway. Chapa's own processing fees are charged to the platform (the system), not passed directly to the customer or vendor.

**8.2 Split Payments**

On every successful payment, Chapa automatically splits funds into two accounts:

- Platform account: receives the service commission (e.g., 5% of the booking amount).
- Vendor/owner account (Chapa subaccount): receives the remainder (e.g., 95%).

**Important:** The split is calculated only on the booking amount, not on add-ons.

**8.3 Walk-In Exclusion**

For walk-in customer bookings processed by staff at the venue, no platform commission is deducted. The full amount goes to the hotel or vendor. But if the staff decided to use Chapa as there payment method they will pay the service fee demanded by Chapa gateway for every successful transaction.

**8.4 Contact-Reveal Payments (Car/House Sales)**

For car and house sale listings, when a buyer requests the seller's contact details, they pay a contact-reveal fee. After payment confirmation, the platform shares the seller's contact. No commission split on the sale transaction itself — the platform's role ends at connection.

**8.5 Individual House Rental Payment Flow**

For unlicensed individual property renters:

- Platform adds its service charge and 15% government tax to the individual's stated price.
- Total (owner price + service charge + 15% tax) is what the client pays.
- Platform remits the tax portion appropriately.

**8.6 No Refunds**

The payment system does not support refunds. This is enforced at the platform level.

**9\. Favorites & Saved Listings**

- Registered users and guests can save (heart/favorite) listings without booking.
- When a listing is saved, a snapshot is captured: current price, photos, and description at that moment.
- If the listing is later modified, the saved snapshot remains unchanged.
- **Deletion Alert:** If a listing that a user has saved or liked (without booking) is deleted from the platform, the user is automatically notified that the listing they saved is no longer available. This applies to all saved/liked-but-not-booked items.

**10\. Availability Management**

**10.1 Hotel / Guesthouse / Event Space**

Day-by-day availability counter maintained per room type or space. When a booking is confirmed, availability is decremented for each booked day. When a booking is cancelled, availability is re-incremented.

**10.2 Car Rental**

Day-by-day availability counter per car listing (tracks units, not individual cars). Supports fleet logic: one listing can represent multiple identical cars. Booking decrements available units; cancellation re-increments them.

**10.3 On/Off Availability Switch**

For hotel staff and property managers, availability can be toggled using a simple on/off switch per room type or per listing per day — no complex calendar management required for basic operations.

**11\. Admin Verification & Listing Control**

- Every listing submitted by a company or individual is reviewed by the platform admin.
- Admin can approve or reject listings with recorded reasons.
- Verified listings display a "Verified by Mechot" badge with the date of verification.
- Unverified listings display a "Not Verified" label but may still be shown (visibility policy TBD).
- Admin can deactivate or remove listings that do not meet standards.

**12\. Notifications**

**12.1 Delivery Channels**

Every notification is sent through two channels simultaneously:

- In-app notification (visible in the Flutter app notification center).
- SMS or push notification via phone (since phone is the primary contact method, not email).

Email notifications can be sent additionally if the user has set up an optional email address.

Users can configure which notifications they receive and through which channel.

**12.2 Customer Notifications**

| **Event** | **Notification** |
| --- | --- |
| Account created | "Welcome to Mechot. Your account is active." |
| Booking created | "Your booking \[REF\] has been received." |
| Booking confirmed | "Your booking at \[Listing\] is confirmed." |
| Booking cancelled | "Your booking \[REF\] has been cancelled." |
| Payment successful | "Payment of \[amount\] ETB confirmed." |
| Payment failed | "Payment unsuccessful, please try again." |
| Saved listing deleted | "A listing you saved is no longer available." |

**12.3 Vendor (Hotel / Owner) Notifications**

| **Event** | **Notification** |
| --- | --- |
| New booking received | "New booking \[REF\] just came in." |
| Booking cancelled | "Booking \[REF\] was cancelled." |
| Payout completed | "\[Amount\] ETB sent to your Chapa account." |

**12.4 Admin Notifications**

| **Event** | **Notification** |
| --- | --- |
| New company registered | "New company registration needs review." |
| New listing submitted | "A new listing has been submitted for review." |
| Company approved/rejected | Confirmation of action taken. |

**13\. Promotional Advertising**

The platform supports promotional ad campaigns that can be configured and managed by the platform admin. Features include:

- Running and scheduling promotions for specific listings or categories.
- Customizing ad placement and duration.
- Ad performance tracking.

Full promotional ad specification is subject to further design, but the system must be built to accommodate this as a first-class admin feature. But the feature must be implemented with minimal way of doing it.

**14\. Legal & Compliance**

**14.1 T&C Versioning**

Every listing owner (hotel, car owner, individual) can upload their own Terms & Conditions. The system versions each upload. When a new version is uploaded, the previous version is archived. Past bookings permanently retain the T&C version they were agreed to at booking time.

**14.2 Permanent Booking Records**

For every booking, the system immutably records:

- Which T&C version was accepted.
- Exact timestamp of acceptance.
- Full copy of the T&C text as it existed at that time.
- Whether the booker was a registered user or a guest.

These records cannot be altered.

**14.3 Individual Owner Licensing**

Private individuals who rent their property through the platform do not hold a rental license. The platform acts as the licensed intermediary. A formal agreement is signed between the platform and the individual owner. The platform collects and remits the applicable 15% government tax on all transactions on their behalf.

**15\. Analytics & Reporting**

**15.1 Vendor Dashboard**

Each vendor (hotel, car owner, individual) has access to a real-time analytics dashboard:

- Revenue today / this week / this month.
- New bookings, confirmed bookings, cancelled bookings.
- Average booking value.
- Top-performing listing or room type.
- Per-day revenue chart (pre-computed for fast load).
- Per-listing breakdown.

**15.2 Pre-Computed Analytics**

Analytics are computed in the background after each booking event, not calculated live on dashboard load. This ensures instant load times regardless of data volume.

**15.3 Admin Dashboard**

Platform-wide view:

- Total transactions.
- Platform revenue (commissions collected).
- Pending company registrations.
- Failed payouts requiring intervention.
- Active listings by category.

**16\. Data Integrity & Historical Accuracy**

The platform follows a strict principle: the past never changes.

| **What Might Change** | **How the System Protects Historical Accuracy** |
| --- | --- |
| Listing price changed | Each booking records the price at booking time. |
| Listing deleted | Booking still shows full details of what was booked. |
| T&C updated | Each booking records which version was agreed to. |
| Add-on menu changed | Each booking records add-on price at booking time. |
| Saved listing changes | Snapshot captures listing state at the time it was saved. |

**17\. Car Rental — Additional Rules**

- Renting with a driver and without a driver are treated as distinct products.
- Without-driver rentals require documentation (driver's license, cheque guarantee and other things). Full document checklist is pending final specification.
- Only Code-3 plate number cars that have a Business License is allowed to be rented.
- Car owners can optionally require renters to fill out a custom form before the rental is finalized.
- Renters can change the rental dates post-booking (subject to availability and T&C).
- Car listings are subject to admin verification. Unverified cars display a "Not Verified" label but still visible.

**18\. Car & House Sales — Connector Model**

The platform does not act as a broker for sales. It acts as a connector:

1.  Buyer views the listing and expresses interest.
2.  Buyer pays a contact-reveal fee.
3.  Upon payment, the seller's contact details are revealed to the buyer.
4.  The actual transaction (negotiation, payment, transfer) takes place directly between buyer and seller outside the platform.

This applies to both car sales and house/property sales. Any type of car and any type of house/property can be listed for sale.

**19\. Guest-to-User Conversion**

Guest users who have placed bookings using only their phone number can later create a registered account. Upon conversion:

- Their full booking history is transferred to their new account.
- Their phone number is used as the linking identifier.
- No history is lost.
- If a user wants to register and enters a phone number that already have a history we will send him/her an OTP to confirm if they are who they are before transferring history.

**20\. Out of Scope / On Hold**

The following items require further specification before development begins:

- Without-driver car rental documentation checklist (driver's license, cheque guarantee, etc.).
- Full detail of the renter form that car owners can optionally require.
- Listing visibility policy for unverified listings (shown with label vs. hidden until verified).
- Full detail of the promotional ad management feature.
- Specific booking date restriction granularity (platform-wide vs. per-category vs. per-listing).

Answers to above

1, Listing visibility policy for unverified listings (shown with label vs. hidden until verified)?

Every listings added by customers are not shown by default they should be in-active and admin reviews it and make it active. So admin can make a listing active but not verify the listing information if they haven’t seen it physically.

Basically being active/in-active affects the listing to be visible to the platform but verified/un-verified does not affect visibility, it just adds a tag.

**21\. Platform Summary**

| **Capability** | **Details** |
| --- | --- |
| Payment Gateway | Chapa |
| Primary Currency | Ethiopian Birr (ETB) |
| Customer Interface | Flutter mobile app + website |
| User Login | Phone number (OTP). Email optional and Password. |
| Vendor Types | Companies + Individual Owners |
| Listing Types | Hotels, Guesthouses, Event Spaces, Car Rentals, Car Sales, House Rentals, House Sales |
| Guest Checkout | Supported. Phone only. History preserved. |
| Service Fee | Applied on booking amount only, not add-ons. Waived on first booking. No fee on walk-ins. |
| Refund Policy | No refunds on any service payment. |
| Payment Split | Chapa splits to platform account + vendor account automatically. |
| Notifications | In-app + SMS/Push. Email if configured. |
| Analytics | Pre-computed, real-time vendor and admin dashboards. |
| Legal Compliance | Full T&C versioning and acceptance audit trail. |
| Listing Verification | Admin-verified badge system with verification date. |
| Unique Value | Enables private individuals to rent/sell their property through a licensed intermediary with tax handled by the platform. |