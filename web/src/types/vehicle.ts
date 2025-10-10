export interface Vehicle {
  id: string;
  make: string;
  model: string;
  year: number;
  price?: number; // Make price optional since it might not always be available
  mileage?: number;
  location?: string;
  image_url?: string | null;
  vin?: string; // VIN for fetching images from auto.dev API
  trim?: string;
  body_style?: string;
  engine?: string;
  transmission?: string;
  exterior_color?: string;
  interior_color?: string;
  doors?: number;
  seating_capacity?: number;
  features?: string[];
  fuel_economy?: {
    city: number;
    highway: number;
    combined: number;
  };
  safety_rating?: {
    overall: number;
    frontal: number;
    side: number;
    rollover: number;
  };
  description?: string;
  dealer_info?: {
    name: string;
    phone: string;
    email: string;
  };
}

export interface VehicleFilters {
  make?: string;
  model?: string;
  year?: string;
  price_min?: number;
  price_max?: number;
  mileage_max?: number;
  body_style?: string;
  transmission?: string;
  state?: string;
  features?: string[];
}
