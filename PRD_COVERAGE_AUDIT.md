### Covered

| Feature | PRD Section | AGENT_TASKS.md task that covers it |
| --- | --- | --- |
| Phone number as the primary login method | `3. Authentication & Identity`; `21. Platform Summary` | `TASK-201`, `TASK-305` |
| Email remains optional rather than required for core flows | `2.1 Customers`; `3. Authentication & Identity`; `21. Platform Summary` | `TASK-201`, `TASK-202` |
| Phone OTP used for account verification flows | `2.1 Customers`; `3. Authentication & Identity` | `TASK-201`, `TASK-202`, `TASK-305` |
| Guest users can interact using phone only without creating an account | `2.2 Guest Users`; `3. Authentication & Identity`; `6.5 Guest Checkout`; `21. Platform Summary` | `TASK-211`, `TASK-216` |
| Guest booking history can later be transferred to a registered account | `2.2 Guest Users`; `6.5 Guest Checkout`; `19. Guest-to-User Conversion` | `TASK-203` |
| Companies self-register and go through admin approval before going live | `2.3 Companies` | `TASK-002`, `TASK-206` |
| Individual owners are admin-managed instead of self-registering | `2.4 Individual Owners` | `TASK-204` |
| Platform admin manages listing verification | `2.5 Platform Admin`; `5. Listing Verification`; `11. Admin Verification & Listing Control`; `21. Platform Summary` | `TASK-205`, `TASK-306` |
| Platform admin monitors transactions | `2.5 Platform Admin` | `TASK-310` |
| Platform admin manages master data such as facilities, amenities, notification templates, and roles | `2.5 Platform Admin` | `TASK-217` |
| Platform admin runs promotional configurations | `2.5 Platform Admin`; `13. Promotional Advertising` | `TASK-307` |
| Hotel room listing domain with amenities, facilities, pricing, add-ons, terms, and availability support | `4.1 Hotel Rooms` | `TASK-001`, `TASK-004`, `TASK-005`, `TASK-006`, `TASK-010` |
| Guesthouse listing domain | `4.2 Guesthouses` | `TASK-001`, `TASK-003`, `TASK-010` |
| Event space listing and booking domain | `4.3 Event Spaces` | `TASK-001`, `TASK-003`, `TASK-007`, `TASK-010` |
| Car rental listing and booking domain | `4.4 Car Rentals` | `TASK-001`, `TASK-003`, `TASK-209`, `TASK-210` |
| With-driver and without-driver car rentals treated as distinct products | `4.4 Car Rentals`; `17. Car Rental - Additional Rules` | `TASK-209` |
| Code-3 plate cars require Business License validation | `4.4 Car Rentals`; `17. Car Rental - Additional Rules` | `TASK-209` |
| Car rental date-change feature after booking | `4.4 Car Rentals`; `17. Car Rental - Additional Rules` | `TASK-210` |
| Car rental listings stay visible while showing verification status tags | `4.4 Car Rentals`; `5. Listing Verification`; `17. Car Rental - Additional Rules` | `TASK-205`, `TASK-206`, `TASK-306` |
| Car sales connector model with contact reveal after payment | `4.5 Car Sales`; `8.4 Contact-Reveal Payments`; `18. Car & House Sales - Connector Model` | `TASK-301` |
| Property rental flow for houses/apartments/rooms | `4.6 House/Property Rentals` | `TASK-303` |
| Individual property rental pricing adds service charge and 15% tax on top of owner price | `4.6 House/Property Rentals`; `8.5 Individual House Rental Payment Flow` | `TASK-304` |
| Individual owner formal agreement/compliance arrangement | `4.6 House/Property Rentals`; `14.3 Individual Owner Licensing` | `TASK-309` |
| Property sales connector model with paid contact reveal | `4.7 House/Property Sales`; `8.4 Contact-Reveal Payments`; `18. Car & House Sales - Connector Model` | `TASK-302` |
| Verified badge / Not Verified label / verification date across listing types | `5. Listing Verification`; `11. Admin Verification & Listing Control`; `21. Platform Summary` | `TASK-205`, `TASK-306` |
| Verification tag does not itself control visibility | `5. Listing Verification`; answer under `20. Out of Scope / On Hold` | `TASK-205`, `TASK-206` |
| New listings default inactive until admin activation | answer under `20. Out of Scope / On Hold` | `TASK-206` |
| Real-time availability checks during booking | `6.1 Booking Flow (General)` | `TASK-003`, `TASK-010` |
| Booking pricing accounts for seasonal logic and multipliers | `6.1 Booking Flow (General)`; `7.1 Seasonal Pricing` | `TASK-003`, `TASK-005` |
| Add-ons can be selected during booking | `6.1 Booking Flow (General)`; `7.2 Add-On Pricing` | `TASK-006` |
| Terms must be accepted before booking and versioned snapshots retained | `6.1 Booking Flow (General)`; `14.1 T&C Versioning`; `14.2 Permanent Booking Records` | `TASK-004` |
| Booking created in pending state with booking reference before payment | `6.1 Booking Flow (General)` | `TASK-003`, `TASK-008` |
| First booking by phone number waives service fee across guest and registered flows | `6.2 Service Charge on First Booking`; `21. Platform Summary` | `TASK-207` |
| Phone-change abuse controls: max three changes and one-week cooldown | `6.2 Service Charge on First Booking` | `TASK-208` |
| Service charge applies only to core booking amount, not add-ons | `6.3 Service Charge Scope`; `7.2 Add-On Pricing`; `8.2 Split Payments`; `21. Platform Summary` | `TASK-214` |
| Walk-in bookings can be created by staff | `6.4 Walk-In Customers` | `TASK-007` |
| Walk-in bookings have no platform commission | `6.4 Walk-In Customers`; `8.3 Walk-In Exclusion`; `21. Platform Summary` | `TASK-007`, `TASK-214` |
| Guest checkout preserved by phone identity | `6.5 Guest Checkout`; `19. Guest-to-User Conversion`; `21. Platform Summary` | `TASK-203`, `TASK-211` |
| Guest bookings require OTP legitimacy verification | `6.5 Guest Checkout` | `TASK-211`, `TASK-305` |
| Forward booking restriction window with default and override support | `6.6 Booking Date Restriction`; resolved note under `20. Out of Scope / On Hold` | `TASK-212` |
| No-refund rule enforced and communicated in booking/payment flows | `6.7 No Refunds`; `8.6 No Refunds`; `21. Platform Summary` | `TASK-213` |
| Seasonal pricing CRUD and rule evaluation | `7.1 Seasonal Pricing` | `TASK-005` |
| Add-ons priced separately from base booking totals | `7.2 Add-On Pricing` | `TASK-006`, `TASK-214` |
| Chapa is the exclusive payment gateway | `8.1 Payment Gateway`; `21. Platform Summary` | `TASK-008` |
| Split payments between platform and vendor | `8.2 Split Payments`; `21. Platform Summary` | `TASK-008`, `TASK-214` |
| Contact-reveal payment flow for sales listings | `8.4 Contact-Reveal Payments`; `18. Car & House Sales - Connector Model` | `TASK-301`, `TASK-302` |
| Favorites/save listings support | `9. Favorites & Saved Listings` | `TASK-009`, `TASK-216` |
| Favorites snapshot remains unchanged after listing changes | `9. Favorites & Saved Listings`; `16. Data Integrity & Historical Accuracy` | `TASK-009` |
| Deletion alert for saved listings | `9. Favorites & Saved Listings`; `12.2 Customer Notifications` | `TASK-218` |
| Day-by-day availability counters for rooms/spaces | `10.1 Hotel / Guesthouse / Event Space` | `TASK-010` |
| Day-by-day car rental availability counters including fleet logic | `10.2 Car Rental` | `TASK-010` |
| Simple on/off availability management for staff/managers | `10.3 On/Off Availability Switch` | `TASK-010` |
| Admin can deactivate listings that should not be visible | `11. Admin Verification & Listing Control` | `TASK-206` |
| Notification center and notification preferences APIs | `12. Notifications` | `TASK-012`, `TASK-215` |
| Notifications delivered through in-app plus SMS/push with optional email | `12.1 Delivery Channels`; `21. Platform Summary` | `TASK-215` |
| Customer notification event coverage | `12.2 Customer Notifications` | `TASK-012`, `TASK-215`, `TASK-218` |
| Vendor notification event coverage | `12.3 Vendor (Hotel / Owner) Notifications` | `TASK-012`, `TASK-215` |
| Admin notification event coverage | `12.4 Admin Notifications` | `TASK-012`, `TASK-215` |
| Promotional campaigns for listings/categories with scheduling and performance tracking | `13. Promotional Advertising` | `TASK-307` |
| T&C versioning with archive behavior | `14.1 T&C Versioning` | `TASK-004` |
| Permanent booking records include T&C version, acceptance timestamp, full T&C text, and guest/registered identity context | `14.2 Permanent Booking Records` | `TASK-004`, `TASK-203` |
| Vendor analytics dashboard metrics | `15.1 Vendor Dashboard` | `TASK-011` |
| Analytics are precomputed in the background instead of only live-calculated | `15.2 Pre-Computed Analytics`; `21. Platform Summary` | `TASK-219` |
| Admin dashboard metrics | `15.3 Admin Dashboard` | `TASK-308` |
| Saved listing historical snapshot integrity | `16. Data Integrity & Historical Accuracy` | `TASK-009` |
| T&C historical integrity on bookings | `16. Data Integrity & Historical Accuracy` | `TASK-004` |
| Guest-to-user conversion must verify existing phone-linked history with OTP | `19. Guest-to-User Conversion` | `TASK-203`, `TASK-305` |
| Full regression and Flutter contract validation after implementation | cross-cutting operational requirement | `TASK-FINAL` |

### Not Covered (gaps)

| Feature | PRD Section | Reason it was likely missed |
| --- | --- | --- |
| Explicit booking-price snapshot test/implementation when later listing prices change | `7.3 Historical Price Preservation`; `16. Data Integrity & Historical Accuracy` | The tasks cover booking lifecycle and seasonal pricing, but no task explicitly targets immutable booked base-price snapshots after later owner price edits. |
| Explicit add-on price snapshot preservation after add-on menu changes | `16. Data Integrity & Historical Accuracy` | `TASK-006` covers add-on CRUD and pricing separation, but there is no direct task for freezing add-on prices onto historical bookings when add-on catalog prices change later. |
| Booking record retains full listing details even if the source listing is later deleted | `16. Data Integrity & Historical Accuracy` | Existing tasks cover saved-listing deletion alerts and booking lifecycle, but none explicitly call out booking-detail snapshot persistence across listing deletion. |
| Listing rejection flow with recorded reasons for admin review | `11. Admin Verification & Listing Control` | Tasks cover verification metadata, activation defaults, and verify/unverify actions, but no task directly mentions reject-with-reason behavior for listings themselves. |
| Admin removal workflow details separate from simple deactivation | `11. Admin Verification & Listing Control` | `TASK-206` addresses inactive defaults and visibility control, but the PRD also mentions removal; no direct task defines safe removal semantics, audit trail, or downstream side effects. |
| Chapa processing-fee burden stays on the platform rather than being passed to customer/vendor | `8.1 Payment Gateway` | Payment integration and split logic are covered, but no task explicitly checks or implements provider-fee allocation at the platform accounting level. |
| In-person verification workflow details for individual owners before profile/staff creation | `2.4 Individual Owners` | `TASK-204` restricts onboarding to admin-managed creation, but it does not explicitly define the offline verification checklist/process described in the PRD. |
| Without-driver car-rental documentation checklist detail | `4.4 Car Rentals`; `17. Car Rental - Additional Rules`; `20. Out of Scope / On Hold` | The PRD itself says the full checklist is pending final specification, so the tasks stop at general compliance validation rather than a finalized checklist workflow. |
| Full customizable renter-form specification for owner-required car rental forms | `4.4 Car Rentals`; `17. Car Rental - Additional Rules`; `20. Out of Scope / On Hold` | `TASK-209` mentions owner-defined pre-rental constraints, but the PRD says the full renter-form detail is still on hold, so there is no direct end-to-end task for a finalized dynamic form system. |
| Full promotional ad-management detail beyond a minimal first-class module | `13. Promotional Advertising`; `20. Out of Scope / On Hold` | `TASK-307` covers a minimal promotional module, but the PRD explicitly says the full advertising specification is still subject to further design. |
