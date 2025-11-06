# Unified Vehicle Listings Schema

The `unified_vehicle_listings` table combines the most complete attributes from the Auto.dev and Marketcheck listing APIs so that both feeds can be queried with the same column set. Every record keeps a `source` flag (`autodev` or `marketcheck`) together with the raw JSON response, making it possible to trace fields back to the original payloads.

## Dataset GDrive Link: https://drive.google.com/drive/folders/17TqIRStI9mwEvcshx4jjzqiN9rLfTcZZ?usp=sharing
uni_vehicles.db: Marketcheck + Autodev vehicles. 167,760 vehicles. Include Carvana listings (Online, no location info)
uni_marketcheck_vehicles.db: Marketcheck vehicles only. 51,518 vehicles, seems to match marketshare in CA more. 

## Column reference

| Column | Type | Description | Primary sources |
| --- | --- | --- | --- |
| `vin` | TEXT PRIMARY KEY | Vehicle Identification Number. Used as the canonical deduplication key. | Auto.dev `vehicle.vin`, Marketcheck `vin` |
| `listing_id` | TEXT | Upstream listing identifier when supplied. | Marketcheck `id`
| `heading` | TEXT | Human-readable listing title or headline. | Marketcheck `heading`
| `source` | TEXT NOT NULL | Originating dataset for the normalized row (`autodev` or `marketcheck`). | Derived
| `price` | INTEGER | Asking price in whole USD. | Auto.dev `retailListing.price`, Marketcheck `price`
| `mileage` | INTEGER | Odometer reading in miles. | Auto.dev `retailListing.miles`, Marketcheck `miles`
| `msrp` | INTEGER | Manufacturer Suggested Retail Price when reported. | Marketcheck `msrp`
| `ref_price` | INTEGER | Marketcheck benchmark price used for delta calculations. | Marketcheck `ref_price`
| `price_change_percent` | REAL | Percent change from `ref_price`. | Marketcheck `price_change_percent`
| `ref_price_dt` | INTEGER | UNIX timestamp when `ref_price` was captured. | Marketcheck `ref_price_dt`
| `ref_miles` | INTEGER | Market benchmark mileage value. | Marketcheck `ref_miles`
| `ref_miles_dt` | INTEGER | Timestamp for `ref_miles`. | Marketcheck `ref_miles_dt`
| `listing_created_at` | TEXT | ISO timestamp for when Auto.dev first saw the listing. | Auto.dev `createdAt`
| `online` | INTEGER | Boolean flag marking whether the Auto.dev listing is currently online. | Auto.dev `online`
| `first_seen_at` | INTEGER | UNIX timestamp of first Marketcheck sighting. | Marketcheck `first_seen_at`
| `first_seen_at_date` | TEXT | ISO date string for `first_seen_at`. | Marketcheck `first_seen_at_date`
| `first_seen_at_source` | INTEGER | Upstream source timestamp for Marketcheck. | Marketcheck `first_seen_at_source`
| `first_seen_at_source_date` | TEXT | ISO date for `first_seen_at_source`. | Marketcheck `first_seen_at_source_date`
| `first_seen_at_mc` | INTEGER | Marketcheck timestamp for when the listing entered their marketplace. | Marketcheck `first_seen_at_mc`
| `first_seen_at_mc_date` | TEXT | ISO date string for `first_seen_at_mc`. | Marketcheck `first_seen_at_mc_date`
| `last_seen_at` | INTEGER | Last time Marketcheck observed the listing. | Marketcheck `last_seen_at`
| `last_seen_at_date` | TEXT | ISO date string for `last_seen_at`. | Marketcheck `last_seen_at_date`
| `scraped_at` | INTEGER | Unix timestamp for the most recent Marketcheck scrape. | Marketcheck `scraped_at`
| `scraped_at_date` | TEXT | ISO date string for `scraped_at`. | Marketcheck `scraped_at_date`
| `data_fetched_at` | TEXT | UTC timestamp when the unified pipeline saved the row. | Derived
| `year` | INTEGER | Model year. | Auto.dev `vehicle.year`, Marketcheck `build.year`
| `make` | TEXT | Manufacturer (capitalization preserved from feed). | Auto.dev `vehicle.make`, Marketcheck `build.make`
| `model` | TEXT | Model name. | Auto.dev `vehicle.model`, Marketcheck `build.model`
| `trim` | TEXT | Trim or sub-model designation. | Auto.dev `vehicle.trim`, Marketcheck `build.trim`
| `body_style` | TEXT | Auto.dev body style term. | Auto.dev `vehicle.bodyStyle`
| `drivetrain` | TEXT | Drivetrain configuration (FWD, AWD, etc.). | Auto.dev `vehicle.drivetrain`, Marketcheck `build.drivetrain`
| `engine` | TEXT | Engine description. | Auto.dev `vehicle.engine`, Marketcheck `build.engine`
| `fuel_type` | TEXT | Fuel type (Gasoline, Electric, Hybrid, ...). | Auto.dev `vehicle.fuel`, Marketcheck `build.fuel_type`
| `transmission` | TEXT | Transmission description. | Auto.dev `vehicle.transmission`, Marketcheck `build.transmission`
| `doors` | INTEGER | Number of doors. | Auto.dev `vehicle.doors`, Marketcheck `build.doors`
| `seats` | INTEGER | Seating capacity. | Auto.dev `vehicle.seats`
| `exterior_color` | TEXT | Exterior color string. | Auto.dev `vehicle.exteriorColor`, Marketcheck `exterior_color`
| `interior_color` | TEXT | Interior color string. | Auto.dev `vehicle.interiorColor`, Marketcheck `interior_color`
| `base_ext_color` | TEXT | Normalized exterior color family. | Marketcheck `base_ext_color`
| `base_int_color` | TEXT | Normalized interior color family. | Marketcheck `base_int_color`
| `build_year` | INTEGER | Year from Marketcheck build section (defaults to Auto.dev year when missing). | Marketcheck `build.year`
| `build_make` | TEXT | Make from build data. | Marketcheck `build.make`
| `build_model` | TEXT | Model from build data. | Marketcheck `build.model`
| `build_trim` | TEXT | Trim from build data. | Marketcheck `build.trim`
| `build_version` | TEXT | Detailed Marketcheck trim or configuration. | Marketcheck `build.version`
| `build_body_type` | TEXT | Body type from Marketcheck build section. | Marketcheck `build.body_type`
| `build_vehicle_type` | TEXT | Vehicle classification (e.g., car, truck, suv). | Marketcheck `build.vehicle_type`
| `build_transmission` | TEXT | Transmission from build section. | Marketcheck `build.transmission`
| `build_drivetrain` | TEXT | Drivetrain from build section. | Marketcheck `build.drivetrain`
| `build_fuel_type` | TEXT | Fuel type from build section. | Marketcheck `build.fuel_type`
| `build_engine` | TEXT | Engine from build section. | Marketcheck `build.engine`
| `build_doors` | INTEGER | Doors from build section. | Marketcheck `build.doors`
| `build_cylinders` | INTEGER | Number of engine cylinders. | Marketcheck `build.cylinders`
| `build_std_seating` | TEXT | Seating configuration label. | Marketcheck `build.std_seating`
| `build_highway_mpg` | INTEGER | Highway MPG figure. | Marketcheck `build.highway_mpg`
| `build_city_mpg` | INTEGER | City MPG figure. | Marketcheck `build.city_mpg`
| `seller_type` | TEXT | Dealer classification (dealer vs. private). | Marketcheck `seller_type`
| `inventory_type` | TEXT | Inventory segment (new, used, cpo, fleet, etc.). | Marketcheck `inventory_type`, Auto.dev derived from `retailListing.used`
| `availability_status` | TEXT | Marketcheck inventory availability state. | Marketcheck `availability_status`
| `is_certified` | INTEGER | Certified Pre-Owned flag. | Marketcheck `is_certified`, Auto.dev `retailListing.cpo`
| `is_cpo` | INTEGER | Alias for `is_certified` (kept for Marketcheck parity). | Derived
| `is_used` | INTEGER | Boolean indicator for used vehicles. | Auto.dev `retailListing.used`, Marketcheck `inventory_type`. 1 is used, 0 is new.
| `in_transit` | INTEGER | Marks listings still in transit to the lot. | Marketcheck `in_transit`
| `model_code` | TEXT | Manufacturer model code. | Marketcheck `model_code`
| `stock_number` | TEXT | Dealer stock identifier. | Auto.dev `retailListing.stockNumber`, Marketcheck `stock_no`
| `dealer_name` | TEXT | Dealer or seller name. | Auto.dev `retailListing.dealer`, Marketcheck `dealer.name`
| `dealer_city` | TEXT | City where the dealer is located. | Auto.dev `retailListing.city`, Marketcheck `dealer.city`
| `dealer_state` | TEXT | Dealer state or province. | Auto.dev `retailListing.state`, Marketcheck `dealer.state`
| `dealer_zip` | TEXT | Dealer postal/ZIP code. | Auto.dev `retailListing.zip`, Marketcheck `dealer.zip`
| `dealer_phone` | TEXT | Dealer phone number. | Auto.dev `retailListing.phone`, Marketcheck `dealer.phone`
| `dealer_latitude` | REAL | Dealer latitude. | Auto.dev `location[1]`, Marketcheck `dealer.latitude`
| `dealer_longitude` | REAL | Dealer longitude. | Auto.dev `location[0]`, Marketcheck `dealer.longitude`
| `dealer_country` | TEXT | Country of the dealer. | Marketcheck `dealer.country`
| `dealer_type` | TEXT | Marketcheck dealer type classification. | Marketcheck `dealer.dealer_type`
| `dealer_msa_code` | TEXT | Metropolitan Statistical Area code. | Marketcheck `dealer.msa_code`
| `dist` | REAL | Distance from the search origin when provided. | Marketcheck `dist`
| `vdp_url` | TEXT | Vehicle detail page URL. | Auto.dev `retailListing.vdp`, Marketcheck `vdp_url`
| `carfax_url` | TEXT | Direct Carfax link if supplied. | Auto.dev `retailListing.carfaxUrl`
| `primary_image_url` | TEXT | First image URL for the listing. | Auto.dev `retailListing.primaryImage`, Marketcheck `media.photo_links[0]`
| `photo_count` | INTEGER | Total number of listing photos. | Auto.dev `retailListing.photoCount`, Marketcheck `media.photo_links`
| `media_json` | TEXT | JSON blob of Marketcheck media assets. | Marketcheck `media`
| `financing_options_json` | TEXT | Serialized financing offers. | Marketcheck `financing_options`
| `leasing_options_json` | TEXT | Serialized leasing offers. | Marketcheck `leasing_options`
| `dealer_json` | TEXT | Raw dealer sub-document. | Marketcheck `dealer`
| `mc_dealership_json` | TEXT | Additional Marketcheck dealership metadata. | Marketcheck `mc_dealership`
| `build_json` | TEXT | Serialized Marketcheck build payload. | Marketcheck `build`
| `data_source` | TEXT | Provider reference for the upstream payload. | Marketcheck `data_source`, defaulted for Auto.dev
| `carfax_one_owner` | INTEGER | Flag for single-owner history. | Marketcheck `carfax_1_owner`
| `carfax_clean_title` | INTEGER | Flag for clean title history. | Marketcheck `carfax_clean_title`
| `dom` | INTEGER | Days on Market metric. | Marketcheck `dom`
| `dom_180` | INTEGER | 180-day Days on Market. | Marketcheck `dom_180`
| `dom_active` | INTEGER | Active Days on Market. | Marketcheck `dom_active`
| `dos_active` | INTEGER | Days on Site metric. | Marketcheck `dos_active`
| `raw_json` | TEXT NOT NULL | Full upstream payload captured at ingestion time. | Derived

## Related documentation

- [Auto.dev Vehicle Listings API](https://docs.auto.dev/v2/products/vehicle-listings)
- [Marketcheck Inventory Search API](https://docs.marketcheck.com/docs/api/cars/inventory/inventory-search)

These references describe the upstream fields that flow into the unified schema. Any unmapped attributes remain accessible through the stored `raw_json` column.
