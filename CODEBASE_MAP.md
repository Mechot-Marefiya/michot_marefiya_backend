# CODEBASE_MAP

Last updated: 2026-06-15

This map was rebuilt from the live codebase and cross-checked against `schema.yaml`, `AGENT_TASKS.md`, `API_CONTRACT_CHANGELOG.md`, and `APP_POTENTIAL_CHANGE.md`.

Phase labels in this document are normalized as:
- `original`: baseline code before the later task waves
- `Phase 2`: auth, booking, compliance, sales connector, and admin/payment hardening tasks
- `Phase 3`: promotions, maps/discovery, Geoapify migration, and later Chapa expansion work

## 1. Django Apps

### Framework and third-party apps
- `jazzmin`: Django admin theming only.
- `django.contrib.admin`: admin site.
- `django.contrib.auth`: auth framework.
- `django.contrib.contenttypes`: generic relations used across favorites, payments, images, terms, promotions.
- `django.contrib.sessions`, `messages`, `staticfiles`: standard Django infrastructure.
- `rest_framework`: DRF runtime.
- `rest_framework_simplejwt` and `token_blacklist`: JWT auth and refresh-token rotation/blacklisting.
- `drf_spectacular`: OpenAPI schema generation.
- `corsheaders`: CORS middleware.

### `apps.account`
- Purpose: user identity, phone-first OTP auth, company and owner profiles, hotel profiles, staff, agreements, and location/profile utilities.
- Models:
  - `Role`: `name CharField`, `code CharField(unique constraint)`, `parent FK self`.
  - `User`: custom auth user with `email EmailField(unique)`, `phone CharField`, `phone_verified_at DateTimeField`, `phone_change_count PositiveSmallIntegerField`, `phone_last_changed_at DateTimeField`, `last_known_lat DecimalField`, `last_known_lng DecimalField`, `location_updated_at DateTimeField`, `location_permission_granted BooleanField`, `role FK Role`, `company FK CompanyProfile`, `individual_owner FK IndividualOwnerProfile`, generic `workspace_content_type/workspace_object_id/workspace`. Uses `CustomUserManager`. Enforces at-most-one employer.
  - `OtpChallenge`: `user FK User nullable`, `phone`, `purpose`, `code_hash`, `expires_at`, `consumed_at`, `attempts`, `max_attempts`, `sent_at`. Indexed by phone/purpose and user/purpose.
  - `ListingImage`: generic image with `content_type/object_id/content_object`, `image ImageField`, `alt_text`, `is_primary`.
  - `CompanyProfile`: `user OneToOne`, `name`, `phone`, `logo`, `license`, `category`, `tin`, `business_license_number`, `description`, `address OneToOne Address`, `status`, `approved_at`, `approved_by FK User`, `rejection_reason`, `chapa_subaccount_id`, `split_type`, `split_value`, `split_config_active`.
  - `IndividualOwnerProfile`: `first_name`, `last_name`, `address OneToOne Address`, `phone unique`, `national_id_number`, `chapa_subaccount_id`, `split_type`, `split_value`, `split_config_active`.
  - `OwnerComplianceAgreement`: `owner FK IndividualOwnerProfile`, `status`, `signed_at`, `signed_by_admin FK User`, `agreement_version`, `note`.
  - `HotelProfile`: inherits `GeoLocatedModel`; `company FK CompanyProfile`, `name`, `description`, `phone`, `website`, `logo`, `license`, `address OneToOne Address`, generic `images`, `is_active`, `is_verified`, `verified_at`, `verified_by FK User`, `verification_note`, `stars`, `facilities M2M Facility`, `featured`.
- Serializers:
  - Auth and OTP: `CustomTokenObtainPairSerializer`, `OtpRequestSerializer`, `OtpResponseSerializer`, `OtpVerifySerializer`.
  - User: `UserSerializer` writes `email/password/confirm_password/first_name/last_name/phone`; `UserResponseSerializer` exposes identity, role, workspace, phone verification data; `UserUpdateSerializer`; `ChangePasswordSerializer`; `GuestBookingConversionSerializer`.
  - Role and staff: `RoleSerializer`, `StaffResponseSerializer`, `StaffCreateSerializer`.
  - Profiles: `CompanyProfileSerializer`, `CompanyProfileResponseSerializer`, `CompanyApplicationSerializer`, `CompanyRegistrationSerializer`, `IndividualOwnerProfileSerializer`, `IndividualOwnerProfileResponseSerializer`, `IndividualOwnerRegistrationSerializer`, `HotelProfileSerializer`, `HotelProfileResponseSerializer`, `AgreementStatusSerializer`, `OwnerComplianceAgreement*` serializers.
  - Utility: `ListingImageSerializer`, `UserLocationSerializer`, password-reset and email-verification serializers.
  - Writable vs read-only: response serializers are read-heavy; creation/update serializers preserve existing API shapes while resolving place/address data and phone-first defaults.
- Views:
  - Auth views: `CustomTokenObtainPairView`, `CustomTokenRefreshView`, `LogoutView`, `OtpRequestView`, `OtpVerifyView`, `MeView`.
  - API views: `UserLocationView`, `PasswordResetView`, `PasswordResetConfirmView`, `VerifyEmailView`, `VerifyEmailChangeView`, `OwnerProfileAgreementView`.
  - ViewSets: `UserViewSet`, `CompanyProfileViewSet`, `IndividualOwnerProfileViewSet`, `HotelProfileViewSet`, `StaffViewSet`, `RoleViewSet`.
  - Custom actions include `users/me`, `users/me/change-password`, `users/me/convert-guest-bookings`, `companies/apply`, `companies/{pk}/approve`, `companies/{pk}/reject`, `individual-owners/{pk}/agreement`, `agreement/sign`, `agreement/revoke`, `hotels/{pk}/check_availability`, `featured`, `verify`, `unverify`, `activate`, `deactivate`, `addons`, and `staff/available-workspaces`.
- URLs:
  - Mounted under `/api/v1/account/`.
  - Auth endpoints mounted in `config/urls.py` under `/api/v1/auth/`.

### `apps.core`
- Purpose: shared base models, addresses, geo fields, facilities, currency rates, conversion, and shared utilities.
- Models:
  - `AbstractBaseModel`: UUID PK, `created_at`, `updated_at`.
  - `GeoLocatedModel`: `latitude`, `longitude`, `formatted_address`, `place_id`, `address_components`; index on lat/lng.
  - `Address`: `street_line1`, `country`, `city`, `sub_city`, `state`, `postal_code`, `latitude`, `longitude`, `google_place_id`.
  - `Facility`: `name unique`, `icon`.
  - `CurrencyRate`: `base`, `target`, `rate`, `date`; unique base/target/date constraint.
- Serializers:
  - `AddressSerializer`, `FacilitySerializer`, `FacilityResponseSerializer`.
  - `FlexibleAddressField`, `JsonSerializerField`, `StringArrayField`.
  - `ConversionInputSerializer`, `CurrencyRateSerializer`, `CurrencyListItemSerializer`, `CurrencyConversionResponseSerializer`.
- Views:
  - `AbstractModelViewSet` limits methods to `get/post/patch/delete`.
  - `FacilityViewSet`: public read, admin write.
  - `CurrencyViewSet`: `list`, `rates`.
  - `CurrencyConvertAPIView`: conversion POST.
- URLs:
  - Mounted under `/api/v1/core/`.

### `apps.listing`
- Purpose: all public listings, booking domains, pricing, inventory, search/discovery, Geoapify-backed map views, and contact reveal flows.
- Models:
  - Shared listing and verification:
    - `BaseListing`: inherits `GeoLocatedModel`; generic `images`, `is_verified`, `verified_at`, `verified_by`, `verification_note`, `title`, `description`, `base_price`, `currency`, `is_active`, `booking_forward_window_days`.
    - `Amenity`: `name unique`, `icon`.
  - Cars:
    - `CarListing`: owner FK to `CompanyProfile` or `IndividualOwnerProfile`, `brand`, `model`, `year`, `mileage`, `fuel_type`, `transmission`, `listing_type`, `rental_mode`, `car_class`, `condition`, `requires_code_3`, `requires_business_license`, `pre_rental_requirements`, `quantity`, `seats`.
    - `CarAvailability`: `car_listing FK`, `date`, `available_units`.
    - `CarRental`: `renter FK nullable`, `start_date`, `end_date`, `total_price`, `currency`, `status`, guest fields, self-drive compliance fields, `booking_reference`, `snapshot`, terms snapshot fields.
    - `CarRentalItem`: `car_rental FK`, `car_listing FK`, `units_rent`, `price_per_unit`.
    - `CarRentalExtensionRequest`: `rental FK`, `requested_by FK User`, `original_end_date`, `requested_end_date`, `extra_days`, `amount`, `currency`, `status`, `tx_ref`, `availability_held`, `expires_at`, `applied_at`, `snapshot`.
    - `CarSaleListing`: car-sale listing with owner FK, car descriptors, `seller_contact_name`, `seller_phone`, `seller_email`, `reveal_fee`.
    - `ContactRevealRequest`: `listing FK CarSaleListing`, `buyer FK User nullable`, `status`, `amount`, `currency`, `buyer_note`, `buyer_phone`, `tx_ref`, `expires_at`, `unlocked_at`, `contact_snapshot`, generic relation to `payment.PaymentTransaction`.
  - Properties:
    - `PropertyListing`: owner FK, `address OneToOne`, `property_type`, `bedrooms`, `bathrooms`, `square_meters`, `is_furnished`.
    - `PropertyRentalAvailability`: `property_listing FK`, `date`, `available_units`, `price`.
    - `PropertyRentalBooking`: `property_listing FK`, `renter FK nullable`, stay dates, totals, status, guest fields, `booking_reference`, snapshot, terms snapshot fields.
    - `PropertySaleListing`: owner FK, `address`, `property_type`, `bedrooms`, `bathrooms`, `square_meters`, `land_size_square_meters`, `is_furnished`, seller contact fields, `reveal_fee`.
    - `PropertyContactRevealRequest`: same state machine pattern as car-sale reveal.
  - Guest houses:
    - `GuestHouseProfile`: owner FK, `address`, `phone`, `website`, `logo`, `license`, `amenities M2M`, `facility M2M`, `rating`.
    - `GuestHouseRoom`: `guest_house FK`, `amenities M2M`, `number_of_guests`, `total_units`, `bed_type`, `room_size_sqm`.
    - `GuestHouseInventory`: `guest_house_room FK`, `date`, `available_rooms`, `price`.
    - `GuestHouseBooking`: guesthouse stay booking with renter/guest fields, terms snapshot, `booking_reference`, status.
    - `GuestHouseBookingItem`: `booking FK`, `room FK`, `units_booked`, `price_per_unit`.
  - Hotels:
    - `RoomListing`: `hotel FK`, `address FK`, `amenities M2M`, `number_of_guests`, `total_units`, `bed_type`, `room_size_sqm`, `smoking_allowed`, `children_allowed`, `refundable`.
    - `RoomInventory`: `room_listing FK`, `date`, `price`.
    - `Booking`: hotel stay booking with booker/guest fields, terms snapshot, `booking_reference`, status.
    - `BookingItem`: `booking FK`, `room FK`, `units_booked`, `price_per_unit`, `snapshot`.
    - `AddonOffering`: `hotel FK`, `name`, `description`, `category`, `price_per_unit`, `currency`, `pricing_type`, `is_active`, `max_quantity_per_booking`, `requires_inventory`, `daily_capacity`, `icon`, `display_order`.
    - `BookingAddon`: `booking_item FK`, optional `offering FK`, snapshot pricing/name/category fields, `quantity`.
    - `BookingRating`: `booking OneToOne`, `rating`, `comment`, `created_at`.
    - `Transaction`: legacy hotel-only transaction model; superseded by `apps.payment.PaymentTransaction`.
    - `StayAvailability`: `hotel FK`, `room FK`, `date`, `available_rooms`.
  - Pricing and terms:
    - `Season`, `SeasonalRate`, `BookingItemPrice`, `TermsAndConditions`.
  - Event spaces:
    - `EventSpaceListing`: `hotel FK`, `address OneToOne`, `amenities M2M`, `number_of_guests`, `total_units`, `space_type`, `floor_area_sqm`.
    - `EventSpaceAvailability`: `space_listing FK`, `date`, `price`, `available_eventspace`.
    - `BookingBase`: abstract event-style booking base.
    - `EventSpaceBooking`: booking base + `event_type` + terms snapshot fields.
    - `EventSpaceBookingItem`: `booking FK`, `event_space FK`, `units_booked`, `price_per_unit`.
- Serializers:
  - Map/location: `AutocompleteResultSerializer`, `PlaceDetailSerializer`, `ReverseGeocodeSerializer`, query serializers for maps.
  - Booking/security helpers: `ForwardBookingWindowMixin`, `SanitizeGuestDetailsMixin`, `GuestBookingOtpRequestSerializer`, `GuestContactRevealOtpRequestSerializer`.
  - Listing response serializers expose additive geo fields, verification fields, favorite state, conversion blocks, and price preview blocks.
  - Booking serializers expose totals, status, item breakdowns, guest data, terms snapshot fields, optional currency conversion, and OTP-linked guest access fields.
  - Contact reveal serializers expose reveal state and never return seller contact before payment verification.
  - Discovery/search serializers: `DiscoveryListingSerializer`, `ProximityListingSerializer`, `ListingSearchResultSerializer`, `SearchSuggestionSerializer`, `MapPinSerializer`.
  - Write serializers preserve existing request shapes and add place resolution, phone verification, and forward booking window validation.
- Views:
  - CRUD/listing families: `RoomListingViewSet`, `GuestHouseProfileViewSet`, `GuestHouseRoomViewSet`, `CarListingViewSet`, `CarSaleListingViewSet`, `PropertySaleListingViewSet`, `PropertyListingViewSet`, `EventSpaceListingViewSet`, `AmenityViewSet`, `AddonOfferingViewSet`, `SeasonViewSet`, `SeasonalRateViewSet`, `TermsAndConditionsViewSet`.
  - Booking families: `BookingViewSet`, `GuestHouseBookingViewSet`, `CarRentalViewSet`, `EventSpaceBookingViewSet`, `PropertyRentalBookingViewSet`.
  - Discovery/maps: `NearbyListingsView`, `WithinBoundsListingsView`, `MapPinsView`, `FeedListingsView`, `ListingSearchView`, `ListingSearchSuggestionsView`, `MapsAutocompleteView`, `MapsPlaceDetailView`, `MapsReverseGeocodeView`.
  - Utility/update views: `StaySearchView`, `InventoryGridView`, `StayAvailabilityUpdateView`, `CarAvailabilitySearchView`, `CarAvailabilityByDateRangeView`, `CarAvailabilityByCarAndDateView`, `CarAvailabilityUpdateAPIView`.
  - Custom actions cover verify/unverify, price previews, walk-in booking, guest OTP request, cancel/partial-cancel, contact request/contact read, lookup, guest-rental access, reschedule, extension preview/initiation, and workspace views.
- URLs:
  - Mounted under `/api/v1/listing/`.
  - Map helper endpoints mounted separately under `/api/v1/maps/`.

### `apps.payment`
- Purpose: Chapa payment initialization/verification/callback/webhook, transaction ledger, split payout metadata, tax calculation, dispute triage, and Chapa subaccount registration.
- Models:
  - `PaymentPlatformConfig`: `name`, `is_active`, `default_split_type`, `default_split_value`, `default_car_sale_reveal_fee`, `default_property_sale_reveal_fee`.
  - `PaymentTransaction`: generic relation fields `content_type/object_id/booking_object`, legacy `booking FK`, `booking_type`, `tx_ref`, `amount`, `currency`, `status`, `chapa_transaction_id`, `payment_method`, `metadata`, `commission_rate`, `commission_amount`, `vendor_payout_amount`, `tax_amount`, `tax_rate`, `tax_liability_status`, dispute triage fields, `payout_status`, `vendor_company FK`, `vendor_individual FK`. `booking` is legacy; `booking_object` is canonical.
- Serializers:
  - `PaymentInitializeSerializer` and `PaymentInitializeResponseSerializer`.
  - `ChapaSubaccountCreateSerializer`, `ChapaSubaccountResponseSerializer`.
  - `PaymentTransactionSerializer`: transaction detail for app-facing verification flows; additive fields now include tax and receipt support.
  - `OwnerPaymentTransactionSerializer`: owner ledger shape.
  - `TransactionMonitorListSerializer`, `TransactionMonitorDetailSerializer`, `DisputeActionSerializer`, `DisputeStatusSerializer`.
  - `ChapaCallbackSerializer`, `ChapaWebhookSerializer`.
- Views:
  - API views: `InitiatePaymentView`, `ChapaSubaccountView`, `ChapaSubaccountMeView`.
  - Function views: `chapa_callback`, `chapa_webhook`, `verify_payment`, `verify_payment_public`, `cancel_payment`.
  - ViewSets: `OwnerPaymentViewSet`, `AdminTransactionMonitorViewSet`.
  - Custom admin dispute actions: `dispute/open`, `dispute`, `dispute/resolve`.
- URLs:
  - Mounted under `/api/v1/payment/`.

### `apps.analytics`
- Purpose: company, front-desk, and admin metrics; precomputed daily metrics; dirty-date tracking.
- Models:
  - `CompanyDailyMetrics`: `company_id`, `date`, `revenue`, `bookings_count`, `confirmed_count`, `cancelled_count`, `avg_booking_value`, `top_listings`.
  - `ListingDailyMetrics`: `listing_id`, `company_id`, `date`, `revenue`, `bookings_count`, `avg_price`.
  - `AnalyticsDirtyDate`: `company_id`, `date`, `processed`.
- Serializers:
  - `OverviewSerializer`, `TimeseriesItemSerializer`, `FrontDeskStatsSerializer`, `FrontDeskAvailability*`, `DateRangeQuerySerializer`, admin metrics serializers.
- Views:
  - `CompanyOverviewView`, `CompanyRevenueView`, `CompanyActivityView`, `FrontDeskStatsView`, `FrontDeskAvailabilityView`, `AdminOverviewMetricsView`, `AdminRevenueMetricsView`, `AdminPayoutFailureMetricsView`.
- URLs:
  - Mounted under `/api/v1/analytics/`.

### `apps.favorites`
- Purpose: authenticated and guest favorites with listing snapshots and later guest-to-user transfer.
- Models:
  - `Favorite`: `user FK`, generic relation target, `snapshot JSONField`, `snapshot_at`.
  - `GuestFavorite`: `guest_phone`, `linked_user FK nullable`, generic relation target, `snapshot`, `snapshot_at`.
- Serializers:
  - `FavoriteSerializer`: `id`, `content_type`, `object_id`, `content_type_display`, `snapshot`, `object`, `created_at`.
  - `GuestFavoriteSerializer`: similar plus `guest_phone`.
- Views:
  - `FavoriteViewSet` with `toggle`.
  - `GuestFavoriteCollectionView`, `GuestFavoriteToggleView`.
- URLs:
  - Mounted under `/api/v1/favorites/`.

### `apps.notifications`
- Purpose: stored notifications, delivery preferences, templates, email/SMS/push task orchestration.
- Models:
  - `Notification`: recipient FK, `notification_type`, `title`, `message`, `metadata`, `action_url`, `is_read`, `read_at`, delivery flags for in-app/email/SMS/push, sent timestamps, `priority`, `expires_at`.
  - `NotificationPreference`: `user OneToOne`, `email_preferences`, `in_app_preferences`, `sms_preferences`, `push_preferences`, `email_enabled`, `sms_enabled`, `push_enabled`.
  - `NotificationTemplate`: template fields for in-app, email, SMS, and push rendering.
- Serializers:
  - `NotificationSerializer`, `NotificationPreferenceSerializer`, `NotificationTemplateSerializer`, `BulkDeleteSerializer`, `BatchMarkReadSerializer`.
- Views:
  - `NotificationViewSet`: list/retrieve/delete plus `mark-read`, `mark-all-read`, `bulk-delete`, `unread-count`, `mark-read-batch`, `summary`.
  - `NotificationPreferenceView`.
  - `NotificationTemplateViewSet` admin CRUD.
- URLs:
  - Mounted under `/api/v1/notifications/`.

### `apps.promotions`
- Purpose: campaign management, placement inventory, click/impression tracking, and public promoted listing feed blocks.
- Models:
  - `PromotionCampaign`: `name`, `advertiser FK User`, `status`, `starts_at`, `ends_at`, `budget`.
  - `PromotionPlacement`: `campaign FK`, `slot_type`, generic target `content_type/object_id/content_object`, `target_category`, `display_order`, `is_active`.
  - `PromotionImpression`: `placement FK`, `user FK nullable`, `ip_address`, `recorded_at`.
  - `PromotionClick`: same shape as impression.
- Serializers:
  - `PromotionCampaignSerializer`, `PromotionCampaignDetailSerializer`.
  - `PromotionPlacementSerializer`.
  - `PublicPlacementSerializer`: public snapshot of promoted listing/category.
  - `TrackingEventSerializer`.
- Views:
  - `PromotionCampaignViewSet` admin CRUD plus nested `placements`.
  - `PublicPromotionPlacementViewSet`.
  - `PromotionTrackingViewSet`.
- URLs:
  - Mounted under `/api/v1/promotions/`.

## 2. Complete API Surface

All routes below are current code routes cross-checked against `schema.yaml`. No obvious schema mismatch was found in the scanned surface.

### Account and Auth
- `POST /api/v1/auth/token/` â†’ `CustomTokenObtainPairView.post`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: JWT pair plus enriched user/role/profile block | Added in: original, deprecated phone-first transition path
- `POST /api/v1/auth/token/refresh/` â†’ `CustomTokenRefreshView.post`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: rotated access/refresh token data | Added in: original
- `POST /api/v1/auth/otp/request/` â†’ `OtpRequestView.post`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: `challenge_id`, `challenge_token`, `cooldown_seconds`, `expires_at` | Added in: Phase 2
- `POST /api/v1/auth/otp/verify/` â†’ `OtpVerifyView.post`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: verification result, optional tokens, guest phone verification token where applicable | Added in: Phase 2
- `POST /api/v1/auth/logout/` â†’ `LogoutView.post`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: refresh blacklist result | Added in: original
- `GET /api/v1/auth/me/` â†’ `MeView.get`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: current user profile | Added in: original
- `GET/POST /api/v1/account/users/` â†’ `UserViewSet.list/create`
  Auth: list yes, create no | Permission: action-based | Flutter-facing: yes | Response: user list or created user with phone-verification state | Added in: original, Phase 2 signup hardening
- `GET/PATCH/DELETE /api/v1/account/users/{id}/` â†’ `UserViewSet.retrieve/partial_update/destroy`
  Auth: yes | Permission: action-based | Flutter-facing: limited | Response: user profile | Added in: original
- `GET/PATCH/PUT/DELETE /api/v1/account/users/me/` â†’ `UserViewSet.me`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: current user update/read | Added in: original
- `POST /api/v1/account/users/me/change-password/` â†’ `UserViewSet.change_password_me`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: success message | Added in: original, behavior updated in Phase 2
- `POST /api/v1/account/users/{id}/change-password/` â†’ `UserViewSet.change_password`
  Auth: yes | Permission: action-based | Flutter-facing: no | Response: success message | Added in: original
- `POST /api/v1/account/users/me/convert-guest-bookings/` â†’ `UserViewSet.convert_guest_bookings`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: linked guest booking/favorite counts | Added in: Phase 2
- `GET/POST /api/v1/account/companies/` â†’ `CompanyProfileViewSet.list/create`
  Auth: list yes, create no | Permission: action-based | Flutter-facing: mostly React/owner | Response: company profile list/create | Added in: original
- `GET/PATCH/DELETE /api/v1/account/companies/{id}/` â†’ `CompanyProfileViewSet.retrieve/partial_update/destroy`
  Auth: yes | Permission: action-based | Flutter-facing: no | Response: company profile detail | Added in: original
- `POST /api/v1/account/companies/apply/` â†’ `CompanyProfileViewSet.apply`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: no | Response: submitted company application | Added in: original
- `POST /api/v1/account/companies/{id}/approve/` â†’ `CompanyProfileViewSet.approve`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: approved profile | Added in: original
- `POST /api/v1/account/companies/{id}/reject/` â†’ `CompanyProfileViewSet.reject`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: rejected profile | Added in: original
- `GET/POST /api/v1/account/hotels/` â†’ `HotelProfileViewSet.list/create`
  Auth: read no, create yes | Permission: action-based | Flutter-facing: detail/list yes, create no | Response: hotel payload with facilities, images, geo, verification | Added in: original, Phase 2/3 additive fields
- `GET/PATCH/DELETE /api/v1/account/hotels/{id}/` â†’ `HotelProfileViewSet.retrieve/partial_update/destroy`
  Auth: read no, write yes | Permission: action-based | Flutter-facing: detail yes | Response: hotel detail | Added in: original
- `GET /api/v1/account/hotels/{id}/check_availability/` â†’ `HotelProfileViewSet.check_availability`
  Auth: no | Permission: public | Flutter-facing: yes | Response: room availability summary | Added in: original
- `GET /api/v1/account/hotels/featured/` â†’ `HotelProfileViewSet.featured`
  Auth: no | Permission: public | Flutter-facing: yes | Response: featured hotels | Added in: original
- `GET /api/v1/account/hotels/{id}/addons/` â†’ `HotelProfileViewSet.addons`
  Auth: yes | Permission: owner/admin | Flutter-facing: no | Response: hotel add-ons | Added in: original
- `POST /api/v1/account/hotels/{id}/verify/` â†’ `HotelProfileViewSet.verify`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: verified hotel | Added in: Phase 2
- `POST /api/v1/account/hotels/{id}/unverify/` â†’ `HotelProfileViewSet.unverify`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: unverified hotel | Added in: Phase 2
- `POST /api/v1/account/hotels/{id}/activate/` â†’ `HotelProfileViewSet.activate`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: activated hotel | Added in: Phase 2
- `POST /api/v1/account/hotels/{id}/deactivate/` â†’ `HotelProfileViewSet.deactivate`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: deactivated hotel | Added in: Phase 2
- `GET/POST /api/v1/account/individual-owners/` â†’ `IndividualOwnerProfileViewSet.list/create`
  Auth: list no, create yes admin-managed | Permission: action-based | Flutter-facing: no | Response: owner profiles | Added in: original, create flow changed in Phase 2
- `GET/PATCH/DELETE /api/v1/account/individual-owners/{id}/` â†’ `IndividualOwnerProfileViewSet.retrieve/partial_update/destroy`
  Auth: read no, write yes | Permission: action-based | Flutter-facing: no | Response: owner detail with agreement status | Added in: original
- `GET/POST/PATCH /api/v1/account/individual-owners/{id}/agreement/` â†’ `IndividualOwnerProfileViewSet.agreement`
  Auth: yes | Permission: action-based | Flutter-facing: no | Response: agreement state | Added in: Phase 2
- `POST /api/v1/account/individual-owners/{id}/agreement/sign/` â†’ `IndividualOwnerProfileViewSet.sign_agreement`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: signed agreement | Added in: Phase 2
- `POST /api/v1/account/individual-owners/{id}/agreement/revoke/` â†’ `IndividualOwnerProfileViewSet.revoke_agreement`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: revoked agreement | Added in: Phase 2
- `GET /api/v1/account/profile/agreement/` â†’ `OwnerProfileAgreementView.get`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes for owner portal, no for regular-user app | Response: current owner agreement status | Added in: Phase 2
- `GET/POST /api/v1/account/staff/` â†’ `StaffViewSet.list/create`
  Auth: yes | Permission: `IsCompanyOwner` | Flutter-facing: no | Response: staff list/create | Added in: original
- `GET/DELETE /api/v1/account/staff/{id}/` â†’ `StaffViewSet.retrieve/destroy`
  Auth: yes | Permission: `IsCompanyOwner` | Flutter-facing: no | Response: staff detail | Added in: original
- `GET /api/v1/account/staff/available-workspaces/` â†’ `StaffViewSet.available_workspaces`
  Auth: yes | Permission: `IsCompanyOwner` | Flutter-facing: no | Response: workspace options | Added in: original
- `GET/POST /api/v1/account/roles/` and `GET/PATCH/DELETE /api/v1/account/roles/{id}/` â†’ `RoleViewSet`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: roles | Added in: Phase 2 admin master-data exposure
- `POST /api/v1/account/password-reset/` â†’ `PasswordResetView.post`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: reset initiation result | Added in: original, now phone-first logic backed | Added in: original
- `POST /api/v1/account/password-reset/confirm/` â†’ `PasswordResetConfirmView.post`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: password reset result | Added in: original
- `POST /api/v1/account/verify-email/` and `POST /api/v1/account/verify-email-change/` â†’ email verification endpoints
  Auth: no | Permission: `AllowAny` | Flutter-facing: low | Response: verification result | Added in: original
- `POST /api/v1/account/location/` â†’ `UserLocationView.post`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: persisted user location state | Added in: Phase 3

### Core
- `GET /api/v1/core/facilities/`, `GET /api/v1/core/facilities/{id}/`, `POST/PATCH/DELETE` same routes for admin â†’ `FacilityViewSet`
  Auth: read no, write yes | Permission: `AllowAny` for read, `IsAdmin` for write | Flutter-facing: read yes | Response: facility objects | Added in: original read, Phase 2 admin write surface
- `GET /api/v1/core/currencies/` â†’ `CurrencyViewSet.list`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: currency code/name list | Added in: original
- `GET /api/v1/core/currencies/rates/` â†’ `CurrencyViewSet.rates`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: latest USD-based rate map | Added in: original
- `POST /api/v1/core/currency/convert/` â†’ `CurrencyConvertAPIView.post`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: converted amount and effective rate | Added in: original

### Listings
- `GET/POST /api/v1/listing/rooms/`, `GET/PATCH/DELETE /api/v1/listing/rooms/{id}/` â†’ `RoomListingViewSet`
  Auth: read no, write yes | Permission: action-based owner/admin | Flutter-facing: yes for read | Response: room listing payload with geo, verification, favorites, price quote | Added in: original
- `GET /api/v1/listing/rooms/{id}/price-preview/` â†’ `RoomListingViewSet.price_preview`
  Auth: no | Permission: public | Flutter-facing: yes | Response: quote for one room | Added in: original
- `GET /api/v1/listing/rooms/availability-matrix/` â†’ `RoomListingViewSet.availability_matrix`
  Auth: yes | Permission: owner/admin | Flutter-facing: no | Response: owner inventory matrix | Added in: original
- `POST /api/v1/listing/rooms/{id}/verify/`, `POST /api/v1/listing/rooms/{id}/unverify/` â†’ admin verify actions
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Added in: Phase 2
- `GET/POST /api/v1/listing/guest-houses/`, `GET/PATCH/DELETE /api/v1/listing/guest-houses/{id}/` â†’ `GuestHouseProfileViewSet`
  Auth: read no, write yes | Permission: action-based | Flutter-facing: yes for read | Response: guesthouse payload | Added in: original
- `GET /api/v1/listing/guest-houses/check-availability/` â†’ `GuestHouseProfileViewSet.check_availability`
  Auth: no | Permission: public | Flutter-facing: yes | Response: guesthouse availability | Added in: original
- `POST /api/v1/listing/guest-houses/{id}/verify/`, `POST /api/v1/listing/guest-houses/{id}/unverify/` â†’ admin verify actions
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Added in: Phase 2
- `GET/POST /api/v1/listing/guest-house-rooms/`, `GET/PATCH/DELETE /api/v1/listing/guest-house-rooms/{id}/` â†’ `GuestHouseRoomViewSet`
  Auth: read no, write yes | Permission: action-based | Flutter-facing: yes for read | Response: guesthouse room payload | Added in: original
- `GET /api/v1/listing/guest-house-rooms/availability-matrix/` â†’ `GuestHouseRoomViewSet.availability_matrix`
  Auth: yes | Permission: owner/admin | Flutter-facing: no | Response: room matrix | Added in: original
- `POST /api/v1/listing/guest-house-rooms/{id}/verify/`, `POST /api/v1/listing/guest-house-rooms/{id}/unverify/` â†’ admin verify actions
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Added in: Phase 2
- `GET/POST /api/v1/listing/cars/`, `GET/PATCH/DELETE /api/v1/listing/cars/{id}/` â†’ `CarListingViewSet`
  Auth: read no, write yes | Permission: action-based | Flutter-facing: yes for read | Response: car listing payload with compliance and geo fields | Added in: original, additive fields in Phase 2/3
- `POST /api/v1/listing/cars/{id}/check_availability/` â†’ `CarListingViewSet.check_availability`
  Auth: no | Permission: public | Flutter-facing: yes | Response: date-range availability | Added in: original
- `GET /api/v1/listing/cars/available_for_rent/` â†’ `CarListingViewSet.available_for_rent`
  Auth: no | Permission: public | Flutter-facing: yes | Response: rentable cars | Added in: original
- `GET /api/v1/listing/cars/my_listings/` â†’ `CarListingViewSet.my_listings`
  Auth: yes | Permission: owner/admin | Flutter-facing: no | Response: owner cars | Added in: original
- `POST /api/v1/listing/cars/{id}/verify/`, `POST /api/v1/listing/cars/{id}/unverify/` â†’ admin verify actions
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Added in: Phase 2
- `GET/POST /api/v1/listing/car-sales/`, `GET /api/v1/listing/car-sales/{id}/` â†’ `CarSaleListingViewSet.list/create/retrieve`
  Auth: read no, create yes | Permission: action-based | Flutter-facing: yes | Response: sale listing with `reveal_state` and payment state context | Added in: Phase 2
- `POST /api/v1/listing/car-sales/{id}/request-contact/` â†’ `CarSaleListingViewSet.request_contact`
  Auth: no for guest flow, yes optional for user | Permission: public with OTP-backed guest path | Flutter-facing: yes | Response: reveal request/payment-init payload | Added in: Phase 2
- `GET /api/v1/listing/car-sales/{id}/contact/` â†’ `CarSaleListingViewSet.contact`
  Auth: conditional by reveal ownership or guest proof | Permission: action-based | Flutter-facing: yes | Response: seller contact only after verified payment | Added in: Phase 2
- `POST /api/v1/listing/car-sales/guest-otp/` â†’ `CarSaleListingViewSet.guest_otp`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: OTP challenge for guest contact reveal | Added in: Phase 2
- `POST /api/v1/listing/car-sales/{id}/verify/`, `POST /api/v1/listing/car-sales/{id}/unverify/` â†’ admin verify actions
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Added in: Phase 2
- `GET/POST /api/v1/listing/properties/`, `GET/PATCH/DELETE /api/v1/listing/properties/{id}/` â†’ `PropertyListingViewSet`
  Auth: read no, write yes | Permission: action-based | Flutter-facing: yes for read | Response: property-rental listing payload | Added in: original
- `POST /api/v1/listing/properties/{id}/verify/`, `POST /api/v1/listing/properties/{id}/unverify/` â†’ admin verify actions
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Added in: Phase 2
- `GET/POST /api/v1/listing/property-sales/`, `GET /api/v1/listing/property-sales/{id}/` â†’ `PropertySaleListingViewSet`
  Auth: read no, create yes | Permission: action-based | Flutter-facing: yes | Response: property-sale listing with reveal state | Added in: Phase 2
- `POST /api/v1/listing/property-sales/{id}/request-contact/` â†’ `PropertySaleListingViewSet.request_contact`
  Auth: no for guest flow, yes optional for user | Permission: public with OTP-backed guest path | Flutter-facing: yes | Response: reveal request/payment-init payload | Added in: Phase 2
- `GET /api/v1/listing/property-sales/{id}/contact/` â†’ `PropertySaleListingViewSet.contact`
  Auth: conditional | Permission: action-based | Flutter-facing: yes | Response: seller contact after verified payment | Added in: Phase 2
- `POST /api/v1/listing/property-sales/guest-otp/` â†’ `PropertySaleListingViewSet.guest_otp`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: OTP challenge | Added in: Phase 2
- `POST /api/v1/listing/property-sales/{id}/verify/`, `POST /api/v1/listing/property-sales/{id}/unverify/` â†’ admin verify actions
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Added in: Phase 2
- `GET /api/v1/listing/amenities/`, `GET /api/v1/listing/amenities/{id}/`, admin write same routes â†’ `AmenityViewSet`
  Auth: read no, write yes | Permission: public read / admin write | Flutter-facing: yes for read | Response: amenity list | Added in: original read, Phase 2 admin write surface
- `GET/POST /api/v1/listing/bookings/`, `GET/PATCH/DELETE /api/v1/listing/bookings/{id}/` â†’ `BookingViewSet`
  Auth: create supports guest/public, list/detail owner/admin | Permission: action-based | Flutter-facing: yes | Response: hotel booking payload with items, totals, status, terms snapshot | Added in: original
- `POST /api/v1/listing/bookings/guest-otp/request/` â†’ `BookingViewSet.guest_otp_request`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: guest booking OTP challenge | Added in: Phase 2
- `GET /api/v1/listing/bookings/lookup/` â†’ `BookingViewSet.lookup`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: guest booking lookup by phone-verified proof | Added in: original, behavior updated in Phase 3
- `POST /api/v1/listing/bookings/price-preview/` â†’ `BookingViewSet.price_preview`
  Auth: no | Permission: public | Flutter-facing: yes | Response: booking preview totals | Added in: original
- `POST /api/v1/listing/bookings/walk-in/` â†’ `BookingViewSet.walk_in`
  Auth: yes | Permission: `IsAuthenticated` with owner/front-desk rules | Flutter-facing: no | Response: created walk-in booking | Added in: original
- `GET /api/v1/listing/bookings/workspace-bookings/` â†’ `BookingViewSet.workspace_bookings`
  Auth: yes | Permission: owner/front-desk | Flutter-facing: no | Response: workspace booking list | Added in: original
- `POST /api/v1/listing/bookings/{id}/cancel/` â†’ `BookingViewSet.cancel`
  Auth: conditional owner/guest | Permission: action-based | Flutter-facing: yes | Response: cancel result with no-refund policy fields | Added in: original, additive policy fields in Phase 2
- `POST /api/v1/listing/bookings/{id}/partial-cancel/` â†’ `BookingViewSet.partial_cancel`
  Auth: yes | Permission: action-based | Flutter-facing: limited | Response: partial cancel result | Added in: original
- `GET/POST /api/v1/listing/guesthouse-bookings/`, `GET/PATCH/DELETE /api/v1/listing/guesthouse-bookings/{id}/` â†’ `GuestHouseBookingViewSet`
  Auth: mixed public create + owner list/detail | Permission: action-based | Flutter-facing: yes | Response: guesthouse booking payload | Added in: original
- `POST /api/v1/listing/guesthouse-bookings/guest-otp/request/`, `GET /api/v1/listing/guesthouse-bookings/lookup/`, `GET /api/v1/listing/guesthouse-bookings/my_bookings/`, `POST /api/v1/listing/guesthouse-bookings/price-preview/`, `POST /api/v1/listing/guesthouse-bookings/walk-in/`, `GET /api/v1/listing/guesthouse-bookings/workspace-bookings/`, `POST /api/v1/listing/guesthouse-bookings/{id}/cancel/`
  Auth: action-based | Flutter-facing: lookup/my-bookings/preview/cancel yes, workspace/walk-in no | Added in: original with Phase 2 guest OTP updates
- `GET/POST /api/v1/listing/bookings-eventspaces/`, `GET/PATCH/DELETE /api/v1/listing/bookings-eventspaces/{id}/` â†’ `EventSpaceBookingViewSet`
  Auth: mixed | Permission: action-based | Flutter-facing: yes | Response: event-space booking payload | Added in: original
- `POST /api/v1/listing/bookings-eventspaces/guest-otp/request/`, `GET /api/v1/listing/bookings-eventspaces/lookup/`, `POST /api/v1/listing/bookings-eventspaces/price-preview/`, `POST /api/v1/listing/bookings-eventspaces/walk-in/`
  Auth: action-based | Flutter-facing: yes except walk-in | Added in: original with Phase 2 guest OTP updates
- `GET/POST /api/v1/listing/car-rentals/`, `GET/PATCH/DELETE /api/v1/listing/car-rentals/{id}/` â†’ `CarRentalViewSet`
  Auth: mixed | Permission: action-based | Flutter-facing: yes | Response: car rental payload including compliance, extension, and payment fields | Added in: original, additive changes in Phase 2/3
- `POST /api/v1/listing/car-rentals/guest-otp/request/`, `GET /api/v1/listing/car-rentals/lookup/`, `GET /api/v1/listing/car-rentals/my_rentals/`, `GET /api/v1/listing/car-rentals/guest-rentals/`, `POST /api/v1/listing/car-rentals/price-preview/`, `GET /api/v1/listing/car-rentals/rental_stats/`
  Auth: action-based | Flutter-facing: lookup/guest-rentals/preview yes, stats no | Added in: original plus later phone-first guest access
- `POST /api/v1/listing/car-rentals/{id}/confirm/`, `POST /api/v1/listing/car-rentals/{id}/cancel/`, `POST /api/v1/listing/car-rentals/{id}/reschedule/`, `POST /api/v1/listing/car-rentals/{id}/extension-price-preview/`, `POST /api/v1/listing/car-rentals/{id}/request-extension/`
  Auth: conditional | Permission: action-based | Flutter-facing: yes | Response: lifecycle updates, extension preview/init result | Added in: original for confirm/cancel, Phase 2 for reschedule, Phase 3 for extension flow
- `GET/POST /api/v1/listing/property-rentals/bookings/`, `GET /api/v1/listing/property-rentals/bookings/{id}/`, `POST /api/v1/listing/property-rentals/bookings/{id}/cancel/`, `POST /api/v1/listing/property-rentals/bookings/price-preview/`, `POST /api/v1/listing/property-rentals/bookings/guest-otp/request/`
  Auth: mixed | Permission: action-based | Flutter-facing: yes | Response: property-rental booking payload and price preview | Added in: Phase 2
- `GET/POST /api/v1/listing/event-spaces/`, `GET/PATCH/DELETE /api/v1/listing/event-spaces/{id}/`, `GET /api/v1/listing/event-spaces/search/`, `POST /api/v1/listing/event-spaces/{id}/verify/`, `POST /api/v1/listing/event-spaces/{id}/unverify/`
  Auth: public read, owner/admin write, admin verify | Flutter-facing: read/search yes | Added in: original, verify in Phase 2
- `GET /api/v1/listing/stays/search/` â†’ `StaySearchView.get`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: hotel search grouped by hotel and available rooms | Added in: original
- `PUT /api/v1/listing/stays/availability/{id}/update/` â†’ `StayAvailabilityUpdateView.put`
  Auth: yes | Permission: owner/admin | Flutter-facing: no | Response: updated availability row | Added in: original
- `GET /api/v1/listing/car-availabilities/by-car-and-date/`, `GET /api/v1/listing/car-availabilities/by-dates/`, `PATCH /api/v1/listing/car-availabilities/{id}/update/`
  Auth: read no, update yes | Permission: public checks / authenticated owner update | Flutter-facing: check endpoints yes | Added in: original
- `GET /api/v1/listing/terms/`, `GET /api/v1/listing/terms/{id}/`, `GET /api/v1/listing/terms/hotel/{hotel_id}/`, `GET /api/v1/listing/terms/guesthouse/{gh_id}/`, `GET /api/v1/listing/terms/company/{company_id}/`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: terms records | Added in: original
- `GET/POST /api/v1/listing/addon-offerings/`, `GET/PATCH/DELETE /api/v1/listing/addon-offerings/{id}/`
  Auth: read no, write yes | Permission: owner/admin | Flutter-facing: read yes | Response: add-on payload | Added in: original
- `GET/POST /api/v1/listing/seasons/`, `GET/PATCH/DELETE /api/v1/listing/seasons/{id}/`, `GET/POST /api/v1/listing/seasonal-rates/`, `GET/PATCH/DELETE /api/v1/listing/seasonal-rates/{id}/`
  Auth: yes | Permission: `IsCompanyOwner` | Flutter-facing: no | Response: season/rate config | Added in: original
- `GET /api/v1/listing/inventory/grid/` â†’ `InventoryGridView.get`
  Auth: yes | Permission: `IsAuthenticated`, `IsListingOwner` | Flutter-facing: no | Response: owner inventory grid | Added in: original
- `GET /api/v1/listing/nearby/`, `GET /api/v1/listing/within-bounds/`, `GET /api/v1/listing/map-pins/`, `GET /api/v1/listing/feed/`, `GET /api/v1/listing/search/`, `GET /api/v1/listing/search/suggestions/`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: discovery/search payloads with `distance_km`, geo fields, map pins, radius context | Added in: Phase 3
- `GET /api/v1/maps/autocomplete/`, `POST /api/v1/maps/place-detail/`, `GET /api/v1/maps/reverse-geocode/`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: Geoapify-backed place helpers | Added in: Phase 3

### Favorites
- `GET/POST /api/v1/favorites/`, `GET/PATCH/DELETE /api/v1/favorites/{id}/`, `POST /api/v1/favorites/toggle/`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: favorite snapshot payload | Added in: original, Phase 2 snapshot alias/additive updates
- `GET/POST /api/v1/favorites/guest/`, `POST /api/v1/favorites/guest/toggle/`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: guest favorites keyed by phone | Added in: Phase 2

### Payments
- `POST /api/v1/payment/initiate/` â†’ `InitiatePaymentView.post`
  Auth: no for guest bookings, yes for registered-user ownership checks | Permission: `AllowAny` + internal ownership rules | Flutter-facing: yes | Response: checkout URL, tx ref, amount/rate audit fields | Added in: original, additive tax/split/audit fields in Phase 2/3
- `GET /api/v1/payment/callback/chapa/` â†’ `chapa_callback`
  Auth: no | Permission: `AllowAny` | Flutter-facing: internal | Response: callback handling result | Added in: original
- `POST /api/v1/payment/webhook/chapa/` â†’ `chapa_webhook`
  Auth: no | Permission: `AllowAny` | Flutter-facing: internal | Response: webhook handling result | Added in: original
- `GET /api/v1/payment/verify/{tx_ref}/` â†’ `verify_payment`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: serialized transaction plus Chapa verification block | Added in: original
- `GET /api/v1/payment/verify-public/{tx_ref}/` â†’ `verify_payment_public`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: transaction or Chapa verification block | Added in: original
- `PUT /api/v1/payment/cancel/{tx_ref}/` â†’ `cancel_payment`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: cancel result with no-refund policy fields | Added in: original, additive policy fields in Phase 2
- `GET /api/v1/payment/ledger/`, `GET /api/v1/payment/ledger/{id}/` â†’ `OwnerPaymentViewSet`
  Auth: yes | Permission: `IsCompanyOwner` | Flutter-facing: no | Response: owner transaction ledger plus summary | Added in: original
- `POST /api/v1/payment/subaccounts/`, `GET /api/v1/payment/subaccounts/me/` â†’ subaccount views
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: vendor app/React yes, regular-user app no | Response: owner subaccount and split config | Added in: Phase 3
- `GET /api/v1/payment/admin/transactions/`, `GET /api/v1/payment/admin/transactions/{id}/`, `POST /api/v1/payment/admin/transactions/{id}/dispute/open/`, `PATCH /api/v1/payment/admin/transactions/{id}/dispute/`, `POST /api/v1/payment/admin/transactions/{id}/dispute/resolve/`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: admin payment monitoring and dispute triage | Added in: Phase 2

### Analytics
- `GET /api/v1/analytics/company/overview/`, `GET /api/v1/analytics/company/revenue/`, `GET /api/v1/analytics/company/activity/`
  Auth: yes | Permission: `IsCompanyOrIndividualOwner` | Flutter-facing: no for regular-user app | Response: owner analytics | Added in: original
- `GET /api/v1/analytics/frontdesk/stats/`, `GET /api/v1/analytics/frontdesk/availability/`
  Auth: yes | Permission: `IsCompanyOrFrontDesk` | Flutter-facing: no | Response: front-desk dashboards | Added in: original
- `GET /api/v1/analytics/admin/overview/`, `GET /api/v1/analytics/admin/revenue/`, `GET /api/v1/analytics/admin/payout-failures/`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: platform admin metrics | Added in: Phase 2

### Notifications
- `GET /api/v1/notifications/`, `GET /api/v1/notifications/{id}/`, `DELETE /api/v1/notifications/{id}/`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: notification items | Added in: original
- `PATCH /api/v1/notifications/{id}/mark-read/`, `POST /api/v1/notifications/mark-all-read/`, `DELETE /api/v1/notifications/bulk-delete/`, `GET /api/v1/notifications/unread-count/`, `POST /api/v1/notifications/mark-read-batch/`, `GET /api/v1/notifications/summary/`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: action wrappers/count/summary | Added in: original
- `GET/PUT /api/v1/notifications/preferences/` â†’ `NotificationPreferenceView`
  Auth: yes | Permission: `IsAuthenticated` | Flutter-facing: yes | Response: preference state | Added in: original
- `GET/POST /api/v1/notifications/templates/`, `GET/PATCH/DELETE /api/v1/notifications/templates/{id}/`
  Auth: yes | Permission: `IsAdmin` | Flutter-facing: no | Response: template CRUD | Added in: Phase 2

### Promotions
- `GET/POST /api/v1/promotions/campaigns/`, `GET/PUT/PATCH/DELETE /api/v1/promotions/campaigns/{id}/`
  Auth: yes | Permission: `IsAuthenticated`, `IsAdmin` | Flutter-facing: no | Response: campaign CRUD | Added in: Phase 3
- `GET/POST /api/v1/promotions/campaigns/{id}/placements/`
  Auth: yes | Permission: `IsAuthenticated`, `IsAdmin` | Flutter-facing: no | Response: campaign placement CRUD-lite | Added in: Phase 3
- `GET /api/v1/promotions/placements/`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: public promoted listing/category placements | Added in: Phase 3
- `POST /api/v1/promotions/track/`
  Auth: no | Permission: `AllowAny` | Flutter-facing: yes | Response: `204 No Content` tracking result | Added in: Phase 3

## 3. Service Layer

Canonical service files currently in use:
- `apps/account/services.py`
  - `ImageCreationService.create_images(content_object, images_payload)`: bulk-create generic images.
  - `OtpService.create_challenge(phone, purpose) -> OtpChallenge`: issue OTP, cache payload, queue SMS.
  - `OtpService.verify_challenge(challenge_id, code, purpose, issue_tokens=False, user=None) -> OtpVerificationResult`: verify OTP, consume challenge, optionally issue JWT.
  - `GuestPhoneVerificationService.create_token(phone) -> str`: signed reusable guest-phone verification token.
  - `GuestPhoneVerificationService.verify_token(token, phone) -> str`: validate signed guest-phone verification token.
  - `GuestBookingConversionService.convert_for_user(user, otp_challenge_id=None, otp_code=None) -> GuestBookingConversionResult`: transfer guest bookings and guest favorites to a registered user.
  - Agreement helpers: `get_latest_agreement`, `create_agreement`, `sign_agreement`, `revoke_agreement`, `is_agreement_active`.
  - External deps: cache/Redis, JWT, SMS task queue.
- `apps/listing/services.py`
  - Listing creation/update helpers: `ListingService` methods for hotel rooms, guest houses, cars, properties, event spaces, address creation, verification, and async geocoding scheduling.
  - OTP wrappers: `GuestBookingOtpService`, `GuestContactRevealOtpService`.
  - Availability services: `StayAvailabilityService`, `GuestHouseAvailabilityService`, property-rental availability helpers, car availability helpers.
  - Booking services: `BookingService`, `GuestHouseBookingService`, `EventSpaceBookingService`, `CarRentalService`, `PropertyRentalBookingService`.
  - Pricing services: `PriceService`, `PriceCalculationService`.
  - Terms services: `TermsService`.
  - External deps: cache, SMS, email helper, notifications, Geoapify geocoding enqueue, payment linkage.
- `apps/payment/services.py`
  - Contact reveal state machine: `ContactRevealPaymentService`.
  - Monitoring/disputes: `get_transaction_monitor_list`, `get_transaction_monitor_detail`, `open_dispute`, `update_dispute`, `resolve_dispute`.
  - Receipt/signature/tax/split helpers: `get_chapa_receipt_url`, `verify_webhook_signature`, `is_tax_applicable`, `calculate_tax`, `get_payment_tax_breakdown`, `apply_tax_to_transaction`, `validate_split_config`, `get_effective_platform_split_config`, `get_effective_contact_reveal_fee`, `resolve_payment_owner_for_split`, `get_effective_split_config_for_owner`, `get_effective_split_config_for_booking`, `register_chapa_subaccount`.
  - Main gateway service: `ChapaPaymentService` for initialize, verify/callback, webhook, cancel, split payout metadata, receipt URL wiring.
  - External deps: Chapa HTTP API, Django settings, payment models, booking models.
- `apps/analytics/services.py`
  - Company overview/revenue/activity live and precomputed reads.
  - Admin metrics cache and aggregation helpers.
  - Cache helpers: `_analytics_cache_key`, `invalidate_analytics_cache`, `precompute_admin_analytics_cache`.
  - External deps: Redis cache, payment transactions, booking models.
- `apps/analytics/services_frontdesk.py`
  - `compute_front_desk_stats`, `get_availability_matrix`.
- `apps/notifications/services.py`
  - `NotificationService.create_notification`, `mark_as_read`, `mark_all_as_read`, `get_unread_count`, `bulk_delete`, `mark_read_batch`.
  - Listing deletion notification planning/dispatch helpers.
  - External deps: email task, SMS task, push task, cache.
- `apps/promotions/services.py`
  - `get_promotable_content_type_ids`, `invalidate_active_placement_cache`, `get_active_placements`, `activate_campaign`, `deactivate_campaign`, `record_impression`, `record_click`.
  - External deps: Redis cache, Celery tracking tasks.
- `apps/core/services/currency_service.py`
  - `CurrencyService.get_daily_exchange_rate`, `get_currencies`, `store_exchange_rates`, `seed_from_local_json`.
  - External deps: Open Exchange Rates API.
- `apps/core/services/email_service.py`
  - `has_deliverable_email`.
  - `EmailService.send_booking_confirmation`, `send_account_credentials`, `send_password_reset`, `send_verification_email`, `send_email_change_verification`, `send_email_change_notice`, `send_notification_email`.
  - `send_payment_receipt` and `send_checkin_reminder` are placeholders.
- `services/maps.py`
  - `geocode_address`, `reverse_geocode`, `autocomplete_address`, `get_place_detail`.
  - `calculate_distance_km`, `get_bounding_box`, `find_listings_near`, `build_map_pin`.
  - External deps: Geoapify HTTP API, Redis cache.
- `services/sms.py`
  - `send_sms(to, message) -> bool`.
  - `normalize_phone_number(phone) -> str`.
  - External deps: AfroMessage HTTP API.
- `services/payment.py`
  - Not present. Canonical payment service remains `apps/payment/services.py`.
- `services/otp.py`
  - Not present. OTP logic lives in `apps/account/services.py`.

## 4. Celery Tasks

- `apps.core.tasks.fetch_daily_exchange_rates`
  - Trigger: periodic beat
  - Purpose: refresh currency rates from Open Exchange Rates
  - Models: `CurrencyRate`
  - Schedule: daily at `00:05`
- `apps.account.tasks.send_otp_sms_task`
  - Trigger: async on OTP creation
  - Purpose: send OTP SMS from cached payload
  - Models: `OtpChallenge`
- `apps.account.tasks.cleanup_expired_otp_challenges`
  - Trigger: periodic beat
  - Purpose: delete expired OTP challenges and related cache keys
  - Models: `OtpChallenge`
  - Schedule: every 5 minutes
- `apps.listing.tasks.auto_cancel_pending_booking`
  - Trigger: async from booking `post_save` signal
  - Purpose: cancel stale hotel bookings
  - Models: `Booking`, `StayAvailability`
- `apps.listing.tasks.auto_cancel_pending_guesthouse_booking`
  - Trigger: async from guesthouse booking `post_save`
  - Purpose: cancel stale guesthouse bookings
  - Models: `GuestHouseBooking`, `GuestHouseInventory`
- `apps.listing.tasks.auto_cancel_pending_property_rental_booking`
  - Trigger: async from property-rental booking `post_save`
  - Purpose: cancel stale property-rental bookings
  - Models: `PropertyRentalBooking`, `PropertyRentalAvailability`
- `apps.listing.tasks.cancel_all_expired_bookings`
  - Trigger: periodic beat
  - Purpose: safety sweep for all pending booking domains above
  - Models: `Booking`, `GuestHouseBooking`, `PropertyRentalBooking`
  - Schedule: every 5 minutes
- `apps.listing.tasks.send_contact_reveal_unlocked_notification`
  - Trigger: async after contact reveal unlock
  - Purpose: create in-app notification and send SMS when reveal is unlocked
  - Models: `ContactRevealRequest`, `PropertyContactRevealRequest`, `Notification`
- `apps.listing.tasks.geocode_listing_async`
  - Trigger: async on listing save or manual backfill
  - Purpose: Geoapify geocode for address-bearing listings
  - Models: address-bearing listing models
  - Retries: `max_retries=3` with backoff `(30, 120, 300)`
- `apps.analytics.tasks.process_dirty_analytics_dates`
  - Trigger: periodic beat
  - Purpose: materialize dirty company-date analytics
  - Models: `AnalyticsDirtyDate`, `CompanyDailyMetrics`, `ListingDailyMetrics`
  - Schedule: every 10 minutes
- `apps.analytics.tasks.precompute_analytics_cache`
  - Trigger: periodic beat
  - Purpose: refresh admin analytics cache
  - Models: `PaymentTransaction`, listing counts via read side
  - Schedule: hourly
- `apps.notifications.tasks.send_notification_email_task`
  - Trigger: async from `NotificationService`
  - Purpose: send email and mark delivery state
  - Models: `Notification`
- `apps.notifications.tasks.send_notification_sms_task`
  - Trigger: async from `NotificationService`
  - Purpose: send SMS and mark delivery state
  - Models: `Notification`
- `apps.notifications.tasks.send_notification_push_task`
  - Trigger: async from `NotificationService`
  - Purpose: push placeholder boundary and mark delivery state
  - Models: `Notification`
- `apps.promotions.tasks.sync_campaign_statuses`
  - Trigger: periodic beat
  - Purpose: activate scheduled campaigns and expire ended ones
  - Models: `PromotionCampaign`, `PromotionPlacement`
  - Schedule: every 5 minutes
- `apps.promotions.tasks.record_impression_async`
  - Trigger: async from placement serving
  - Purpose: persist impressions
  - Models: `PromotionImpression`
- `apps.promotions.tasks.record_click_async`
  - Trigger: async from click tracking
  - Purpose: persist clicks
  - Models: `PromotionClick`

## 5. Authentication and Permissions

- JWT config:
  - Access token lifetime: `30 days` in `DEBUG`, `1 hour` otherwise.
  - Refresh token lifetime: `30 days` in `DEBUG`, `1 day` otherwise.
  - Refresh rotation: enabled.
  - Auth class: `rest_framework_simplejwt.authentication.JWTAuthentication`.
- Phone/OTP config:
  - `OTP_CODE_LENGTH=6`
  - `OTP_EXPIRY_SECONDS=300`
  - `OTP_MAX_ATTEMPTS=5`
  - `OTP_COOLDOWN_SECONDS=60`
  - Guest reusable verification token max age: `GUEST_PHONE_VERIFICATION_MAX_AGE_SECONDS` default `31536000`.
  - Guest booking OTP enforcement default: `REQUIRE_GUEST_BOOKING_OTP=True`.
- Custom permission classes:
  - `IsAdmin`: superuser or `RoleCode.ADMIN`.
  - `IsCompany`: admin or company role.
  - `IsCompanyOrIndividualOwner`: owner-side access across company and individual-owner paths.
  - `IsUser`: regular-user role or admin.
  - `IsOwnerOrReadOnly`, `IsAuthenticatedOrReadOnly`, `IsPublicReadOnly`.
  - `IsCompanyOwner`: owner/admin payment and company object protection.
  - `IsListingOwner`: owner/admin/front-desk listing object access.
  - `IsBookingOwner`, `IsGuestHouseBookingOwner`, `IsCarRentalOwner`, `CanModifyBooking`.
  - `IsCompanyOrFrontDesk`.
  - `ORPermission`: permission combiner.
- Throttles:
  - Auth/login, OTP request/verify, password reset, email verify, availability check, payment init/verify/callback/webhook, token refresh/logout, currency endpoints.

## 6. Redis Usage

- OTP:
  - `otp:pending:{challenge_id}`
  - TTL: `OTP_EXPIRY_SECONDS`
  - Invalidated on send success, verify success, failed send cleanup, periodic cleanup
- OTP cooldown:
  - `otp:cooldown:{phone}:{purpose}`
  - TTL: `OTP_COOLDOWN_SECONDS`
  - Invalidated on verify success, failed send cleanup, periodic cleanup
- Maps/geocoding:
  - `maps:geocode:{sha256(address)}`
  - `maps:reverse:{rounded_lat}:{rounded_lng}`
  - `maps:place:{place_id}`
  - TTL: `GEOCODING_CACHE_TTL`
  - Invalidated by TTL only
- Listing discovery/search:
  - `listing:nearby:{sha256(payload)}`
  - `listing:bounds:{sha256(payload)}`
  - `listing:pins:{sha256(payload)}`
  - `listing:feed:proximity:{sha256(payload)}`
  - `listing:feed:standard:{sha256(payload)}`
  - `search:suggestions:{sha256(payload)}`
  - TTL: `PROXIMITY_CACHE_TTL`, `MAP_PINS_CACHE_TTL`, and suggestions hardcoded `60s`
  - Invalidated by TTL only
- Notifications:
  - `notifications:unread_count:{user_id}`
  - TTL: `3600`
  - Invalidated on notification create, mark-read, mark-all-read, bulk-delete, batch mark-read
- Analytics:
  - Version key: `analytics:admin:version`
  - Data keys: `analytics:v{version}:{metric}:{suffix}`
  - TTL: `ANALYTICS_CACHE_TTL=3600`
  - Invalidated by `invalidate_analytics_cache()`
- Promotions:
  - Version key: `promotions:placements:version`
  - Data keys: `promotions:v{version}:placements:...`
  - TTL: `PROMOTION_CACHE_TTL=300`
  - Invalidated on campaign/placement writes and campaign status transitions

## 7. Maps Integration

- Active provider:
  - Geoapify only. Google Maps backend logic is deprecated and no longer the active path.
- Approach:
  - Decimal lat/lng fields on models.
  - Haversine distance in `services/maps.py`.
  - Bounding-box prefilter + Haversine refinement.
  - No PostGIS or GeoDjango.
- Service:
  - `services/maps.py`
  - Key functions: `geocode_address`, `reverse_geocode`, `autocomplete_address`, `get_place_detail`, `calculate_distance_km`, `get_bounding_box`, `find_listings_near`, `build_map_pin`
- Models with coordinates:
  - `apps.core.Address`
  - `apps.core.GeoLocatedModel` descendants:
    - `apps.account.HotelProfile`
    - `apps.listing.RoomListing`
    - `apps.listing.GuestHouseProfile`
    - `apps.listing.GuestHouseRoom`
    - `apps.listing.CarListing`
    - `apps.listing.CarSaleListing`
    - `apps.listing.PropertyListing`
    - `apps.listing.PropertySaleListing`
    - `apps.listing.EventSpaceListing`
  - User location fields:
    - `apps.account.User.last_known_lat`
    - `apps.account.User.last_known_lng`
- Map-related endpoints:
  - `POST /api/v1/account/location/`
  - `GET /api/v1/maps/autocomplete/`
  - `POST /api/v1/maps/place-detail/`
  - `GET /api/v1/maps/reverse-geocode/`
  - `GET /api/v1/listing/nearby/`
  - `GET /api/v1/listing/within-bounds/`
  - `GET /api/v1/listing/map-pins/`
  - `GET /api/v1/listing/feed/`
  - `GET /api/v1/listing/search/`
  - `GET /api/v1/listing/search/suggestions/`

## 8. Payment Integration (Chapa)

- Canonical service location:
  - `apps/payment/services.py`
- Main capabilities present:
  - Payment initialization
  - Callback verification
  - Webhook verification
  - Public and authenticated verify endpoints
  - Pending transaction cancel
  - Owner ledger
  - Admin monitoring/disputes
  - Platform split config resolution
  - Owner-specific split override
  - Chapa subaccount registration
  - Contact reveal payments
  - Property-rental tax calculation
  - Receipt URL generation
- Webhook endpoint:
  - `POST /api/v1/payment/webhook/chapa/`
- Callback endpoint:
  - `GET /api/v1/payment/callback/chapa/`
- Payment endpoints:
  - `POST /api/v1/payment/initiate/`
  - `GET /api/v1/payment/verify/{tx_ref}/`
  - `GET /api/v1/payment/verify-public/{tx_ref}/`
  - `PUT /api/v1/payment/cancel/{tx_ref}/`
  - `GET /api/v1/payment/ledger/`
  - `GET /api/v1/payment/ledger/{id}/`
  - `POST /api/v1/payment/subaccounts/`
  - `GET /api/v1/payment/subaccounts/me/`
  - `GET /api/v1/payment/admin/transactions/`
  - `GET /api/v1/payment/admin/transactions/{id}/`
  - dispute actions under `/api/v1/payment/admin/transactions/{id}/...`

## 9. SMS Service

- Service:
  - `services/sms.py`
- Public function:
  - `send_sms(to, message) -> bool`
- Used by:
  - `apps.account.tasks.send_otp_sms_task`
  - `apps.listing.tasks.send_contact_reveal_unlocked_notification`
  - `apps.notifications.tasks.send_notification_sms_task`
  - `apps.notifications.services.NotificationService.dispatch_saved_listing_deletion_notifications`
  - booking confirmation SMS-first flow inside `apps/listing/services.py`
- Notes:
  - Provider access is centralized here only.
  - Uses AfroMessage hardcoded send URL and Ethiopian phone normalization.

## 10. Background Tasks Summary

- Beat-scheduled tasks:
  - `apps.core.tasks.fetch_daily_exchange_rates` â†’ daily `00:05`
  - `apps.listing.tasks.cancel_all_expired_bookings` â†’ every 5 minutes
  - `apps.account.tasks.cleanup_expired_otp_challenges` â†’ every 5 minutes
  - `apps.analytics.tasks.process_dirty_analytics_dates` â†’ every 10 minutes
  - `apps.analytics.tasks.precompute_analytics_cache` â†’ every hour
  - `apps.promotions.tasks.sync_campaign_statuses` â†’ every 5 minutes
- Async tasks:
  - OTP SMS delivery
  - notification email/SMS/push
  - hotel/guesthouse/property booking auto-cancel follow-ups
  - contact reveal unlocked notifications
  - async geocoding
  - promotion impression/click writes

## 11. Known Limitations or Follow-ups

- `schema.yaml` and scanned route/view surface appear aligned; no obvious mismatch was found during this pass.
- `services/payment.py` does not exist; any docs pointing there should point to `apps/payment/services.py`.
- `services/otp.py` does not exist; OTP lives in `apps/account/services.py`.
- `apps/listing/services.py` remains the highest-coupling file and contains multiple domains in one place.
- `apps.listing.services.GuestHouseAvailabilityService` was historically duplicated; keep checking the live file before refactors.
- `apps/listing/models.Transaction` is a legacy booking-only transaction model; `apps.payment.models.PaymentTransaction` is the active payment ledger.
- `apps/payment.models.PaymentTransaction.booking` is legacy; `booking_object` is the active generic relation.
- `apps/core.Address.google_place_id` is a legacy name now that Geoapify is the active provider.
- `AFRO_MESSAGE_URL` still exists in settings, but per project rule the SMS service should continue using the hardcoded provider URL in `services/sms.py`.

