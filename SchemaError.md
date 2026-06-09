## Schema Warning Categorization

Source reviewed: captured `drf-spectacular` output in [schema_output.txt](/c:/Users/Surafel/Documents/Project%20Works/Mechot%20IT/Mechot%20Marefiya/Project/michot_marefiya_backend/schema_output.txt)

Precedence used when a route fit multiple buckets: `[BLOCKING]` > `[FLUTTER]` > `[REACT]` > `[COSMETIC]` > `[STANDALONE]`.

| Warning | Endpoint | Category |
| --- | --- | --- |
| `UserResponseSerializer.get_workspace` unresolved in `CompanyProfileResponseSerializer` | `/api/v1/account/companies/`, `/api/v1/account/companies/{id}/` | `[FLUTTER]` |
| `CompanyRegistrationSerializer.address` `FlexibleAddressField()` unresolved | `POST /api/v1/account/companies/` | `[FLUTTER]` |
| `CompanyProfileSerializer.address` `FlexibleAddressField()` unresolved | `PATCH /api/v1/account/companies/{id}/` | `[FLUTTER]` |
| `HotelProfileSerializer.address` `FlexibleAddressField()` unresolved | `/api/v1/account/hotels/*` | `[BLOCKING]` |
| `HotelProfileSerializer.facilities` `JsonSerializerField()` unresolved | `/api/v1/account/hotels/*` | `[BLOCKING]` |
| `StaffResponseSerializer.get_workspace` unresolved | `/api/v1/account/staff/` | `[REACT]` |
| `StaffViewSet` path parameter `id` inferred as string | `/api/v1/account/staff/{id}/` | `[REACT]` |
| `UserResponseSerializer.get_workspace` unresolved in `UserViewSet` | `/api/v1/account/users/*` | `[BLOCKING]` |
| Error: `FrontDeskAvailabilityView` has no serializer | `GET /api/v1/analytics/frontdesk/availability/` | `[BLOCKING]` |
| Error: `CurrencyViewSet` has no serializer | `GET /api/v1/core/currencies/`, `GET /api/v1/core/currencies/rates/` | `[STANDALONE]` |
| Error: `CurrencyConvertAPIView` has no serializer | `POST /api/v1/core/currency/convert/` | `[STANDALONE]` |
| `FavoriteSerializer.get_content_type_display` unresolved | `/api/v1/favorites/` | `[BLOCKING]` |
| `FavoriteSerializer.get_snapshot` unresolved | `/api/v1/favorites/` | `[BLOCKING]` |
| `FavoriteSerializer.get_object` unresolved | `/api/v1/favorites/` | `[BLOCKING]` |
| `FavoriteViewSet` path parameter `id` inferred as string | `/api/v1/favorites/{id}/` | `[BLOCKING]` |
| `GuestFavoriteSerializer.get_content_type_display` unresolved | `/api/v1/favorites/guest/` | `[BLOCKING]` |
| `GuestFavoriteSerializer.get_snapshot` unresolved | `/api/v1/favorites/guest/` | `[BLOCKING]` |
| `GuestFavoriteSerializer.get_object` unresolved | `/api/v1/favorites/guest/` | `[BLOCKING]` |
| `BookingAddonSerializer.subtotal` unresolved | `/api/v1/listing/bookings/*` | `[BLOCKING]` |
| `BookingResponseSerializer.get_is_resumable` unresolved | `/api/v1/listing/bookings/*` | `[BLOCKING]` |
| `EventSpaceBookingItemResponseSerializer.get_nightly_rate` unresolved | `/api/v1/listing/bookings-eventspaces/*` | `[BLOCKING]` |
| `EventSpaceBookingItemResponseSerializer.get_stay_total` unresolved | `/api/v1/listing/bookings-eventspaces/*` | `[BLOCKING]` |
| `EventSpaceBookingItemResponseSerializer.get_subtotal` unresolved | `/api/v1/listing/bookings-eventspaces/*` | `[BLOCKING]` |
| Error: `CarAvailabilityUpdateAPIView` has no serializer | `PATCH /api/v1/listing/car-availabilities/{id}/update/` | `[BLOCKING]` |
| Error: `CarAvailabilityByCarAndDateView` has no serializer | `GET /api/v1/listing/car-availabilities/by-car-and-date/` | `[BLOCKING]` |
| Error: `CarAvailabilityByDateRangeView` has no serializer | `GET /api/v1/listing/car-availabilities/by-dates/` | `[BLOCKING]` |
| `CarRentalItemSerializer.get_car_listing_details` unresolved | `/api/v1/listing/car-rentals/*` | `[BLOCKING]` |
| `CarRentalItemSerializer.get_nightly_rate` unresolved | `/api/v1/listing/car-rentals/*` | `[BLOCKING]` |
| `CarRentalItemSerializer.get_stay_total` unresolved | `/api/v1/listing/car-rentals/*` | `[BLOCKING]` |
| `CarRentalItemSerializer.get_subtotal` unresolved | `/api/v1/listing/car-rentals/*` | `[BLOCKING]` |
| `CarListingResponseSerializer.get_current_availability` unresolved | `/api/v1/listing/cars/*` | `[BLOCKING]` |
| `CarListingResponseSerializer.get_price_quote` unresolved | `/api/v1/listing/cars/*` | `[BLOCKING]` |
| `EventSpaceListingResponseSerializer.get_price_quote` unresolved | `/api/v1/listing/event-spaces/*` | `[BLOCKING]` |
| `EventSpaceListingSerializer.address` `FlexibleAddressField(required=False)` unresolved | `/api/v1/listing/event-spaces/*` | `[BLOCKING]` |
| `EventSpaceListingSerializer.amenities` `JsonSerializerField(required=False)` unresolved | `/api/v1/listing/event-spaces/*` | `[BLOCKING]` |
| `GuestHouseRoomResponseSerializer.get_available_units` unresolved | `/api/v1/listing/guest-house-rooms/*` | `[BLOCKING]` |
| `GuestHouseRoomResponseSerializer.get_price_quote` unresolved | `/api/v1/listing/guest-house-rooms/*` | `[BLOCKING]` |
| `GuestHouseProfileResponseSerializer.get_facility` unresolved | `/api/v1/listing/guest-houses/*` | `[BLOCKING]` |
| `GuestHouseProfileResponseSerializer.get_is_favorite` unresolved | `/api/v1/listing/guest-houses/*` | `[BLOCKING]` |
| `GuestHouseProfileSerializer.amenities` `JsonSerializerField()` unresolved | `/api/v1/listing/guest-houses/*` | `[BLOCKING]` |
| `GuestHouseProfileSerializer.address` `FlexibleAddressField()` unresolved | `/api/v1/listing/guest-houses/*` | `[BLOCKING]` |
| `GuestHouseBookingItemSerializer.get_nightly_rate` unresolved | `/api/v1/listing/guesthouse-bookings/*` | `[BLOCKING]` |
| `GuestHouseBookingItemSerializer.get_stay_total` unresolved | `/api/v1/listing/guesthouse-bookings/*` | `[BLOCKING]` |
| `GuestHouseBookingItemSerializer.get_subtotal` unresolved | `/api/v1/listing/guesthouse-bookings/*` | `[BLOCKING]` |
| Error: `InventoryGridView` has no serializer | `GET /api/v1/listing/inventory/grid/` | `[REACT]` |
| `PropertyListingSerializer.address` `FlexibleAddressField()` unresolved | `/api/v1/listing/properties/*` | `[BLOCKING]` |
| `RoomListingSerializer.address` `FlexibleAddressField(required=False)` unresolved | `/api/v1/listing/rooms/*` | `[BLOCKING]` |
| `SeasonalRateSerializer.get_target_name` unresolved | `/api/v1/listing/seasonal-rates/*` | `[REACT]` |
| Error: `StayAvailabilityUpdateView` has no serializer | `PUT /api/v1/listing/stays/availability/{id}/update/` | `[REACT]` |
| `StaySearchView.SearchResultSerializer.get_is_favorite` unresolved | `GET /api/v1/listing/stays/search/` | `[BLOCKING]` |
| `TermsAndConditionsViewSet` path parameter `company_id` inferred as string | `GET /api/v1/listing/terms/company/{company_id}/` | `[FLUTTER]` |
| `TermsAndConditionsViewSet` path parameter `gh_id` inferred as string | `GET /api/v1/listing/terms/guesthouse/{gh_id}/` | `[FLUTTER]` |
| `TermsAndConditionsViewSet` path parameter `hotel_id` inferred as string | `GET /api/v1/listing/terms/hotel/{hotel_id}/` | `[FLUTTER]` |
| `NotificationViewSet.get_queryset()` fails for schema generation | `/api/v1/notifications/`, `/api/v1/notifications/{id}/` | `[BLOCKING]` |
| `NotificationViewSet` path parameter `id` inferred as string | `/api/v1/notifications/{id}/` | `[BLOCKING]` |
| `NotificationViewSet.mark_read` `OpenApiExample` unresolved | `PATCH /api/v1/notifications/{id}/mark-read/` | `[COSMETIC]` |
| `NotificationViewSet.bulk_delete` first `OpenApiExample` unresolved | `DELETE /api/v1/notifications/bulk-delete/` | `[COSMETIC]` |
| `NotificationViewSet.bulk_delete` second `OpenApiExample` unresolved | `DELETE /api/v1/notifications/bulk-delete/` | `[COSMETIC]` |
| `NotificationViewSet.mark_all_read` `OpenApiExample` unresolved | `POST /api/v1/notifications/mark-all-read/` | `[COSMETIC]` |
| `NotificationViewSet.mark_read_batch` `OpenApiExample` unresolved | `POST /api/v1/notifications/mark-read-batch/` | `[COSMETIC]` |
| `NotificationViewSet.summary` `OpenApiExample` unresolved | `GET /api/v1/notifications/summary/` | `[COSMETIC]` |
| `NotificationViewSet.unread_count` `OpenApiExample` unresolved | `GET /api/v1/notifications/unread-count/` | `[COSMETIC]` |
| `NotificationPreferenceView.put` `OpenApiExample` unresolved | `PUT /api/v1/notifications/preferences/` | `[COSMETIC]` |
| `OwnerPaymentTransactionSerializer.get_booking_reference` unresolved | `/api/v1/payment/ledger/`, `/api/v1/payment/ledger/{id}/` | `[FLUTTER]` |
| `OwnerPaymentTransactionSerializer.get_listing_title` unresolved | `/api/v1/payment/ledger/`, `/api/v1/payment/ledger/{id}/` | `[FLUTTER]` |
| `OwnerPaymentTransactionSerializer.get_customer_name` unresolved | `/api/v1/payment/ledger/`, `/api/v1/payment/ledger/{id}/` | `[FLUTTER]` |
| `OwnerPaymentTransactionSerializer.get_booking_dates` unresolved | `/api/v1/payment/ledger/`, `/api/v1/payment/ledger/{id}/` | `[FLUTTER]` |
| Enum collision: `category` resolved as `Category6daEnum` | Schema component naming for add-on category enums | `[COSMETIC]` |
| Enum collision: `category` resolved as `Category70bEnum` | Schema component naming for company category enums | `[COSMETIC]` |
| Enum collision: `status` resolved as `Status01bEnum` | Schema component naming for booking status enums | `[COSMETIC]` |

