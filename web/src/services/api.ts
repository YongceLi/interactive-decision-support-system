import { ChatRequest, ChatResponse } from '@/types/chat';
import { Vehicle } from '@/types/vehicle';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class IDSSApiService {
  private sessionId: string | null = null;

  async sendMessage(message: string): Promise<ChatResponse> {
    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message,
          session_id: this.sessionId,
        } as ChatRequest),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: ChatResponse = await response.json();
      
      // Store session ID for future requests
      if (data.session_id) {
        this.sessionId = data.session_id;
      }

      return data;
    } catch (error) {
      console.error('Error sending message to IDSS agent:', error);
      throw error;
    }
  }

  async getSession(sessionId?: string): Promise<Record<string, unknown>> {
    try {
      const id = sessionId || this.sessionId;
      if (!id) {
        throw new Error('No session ID available');
      }

      const response = await fetch(`${API_BASE_URL}/session/${id}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Error getting session:', error);
      throw error;
    }
  }

  async resetSession(): Promise<string> {
    try {
      const response = await fetch(`${API_BASE_URL}/session/reset`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: this.sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      if (data.session_id) {
        this.sessionId = data.session_id;
      }

      return data.session_id;
    } catch (error) {
      console.error('Error resetting session:', error);
      throw error;
    }
  }

  getSessionId(): string | null {
    return this.sessionId;
  }

  // Convert API vehicle data to our Vehicle type
  convertVehicle(apiVehicle: Record<string, unknown>): Vehicle {
    // Handle nested auto.dev API structure
    const vehicle = (apiVehicle.vehicle as Record<string, unknown>) || apiVehicle;
    const retailListing = (apiVehicle.retailListing as Record<string, unknown>) || {};
    
    // Extract price from various possible locations
    let price: number | undefined;
    if (retailListing.price) {
      price = retailListing.price as number;
    } else if (retailListing.listPrice) {
      price = retailListing.listPrice as number;
    } else if (apiVehicle.price) {
      price = apiVehicle.price as number;
    }
    
    // Extract mileage from various possible locations
    let mileage: number | undefined;
    if (retailListing.miles) {
      mileage = retailListing.miles as number;
    } else if (vehicle.mileage) {
      mileage = vehicle.mileage as number;
    } else if (apiVehicle.mileage) {
      mileage = apiVehicle.mileage as number;
    }
    
    // Extract location - prefer city/state over coordinates
    let location: string | undefined;
    if (retailListing.city && retailListing.state) {
      location = `${retailListing.city}, ${retailListing.state}`;
    } else if (retailListing.state) {
      location = retailListing.state as string;
    } else if (vehicle.location) {
      location = vehicle.location as string;
    } else if (apiVehicle.location) {
      location = apiVehicle.location as string;
    }
    
    // Extract VIN for image fetching
    const vin = (vehicle.vin as string) || (apiVehicle.vin as string);
    
    // Extract image URL from retailListing.primaryImage (Auto.dev format)
    const image_url = (retailListing.primaryImage as string) || 
                     (vehicle.image_url as string) || 
                     (apiVehicle.image_url as string);
    
    return {
      id: (vehicle.id as string) || (apiVehicle.id as string) || Math.random().toString(36).substr(2, 9),
      make: (vehicle.make as string) || 'Unknown',
      model: (vehicle.model as string) || 'Unknown',
      year: (vehicle.year as number) || new Date().getFullYear(),
      price: price,
      mileage: mileage,
      location: location,
      vin: vin,
      image_url: image_url,
      trim: (vehicle.trim as string) || (apiVehicle.trim as string),
      body_style: (vehicle.bodyStyle as string) || (vehicle.body_style as string) || (apiVehicle.body_style as string),
      engine: (vehicle.engine as string) || (apiVehicle.engine as string),
      transmission: (vehicle.transmission as string) || (apiVehicle.transmission as string),
      exterior_color: (vehicle.exteriorColor as string) || (vehicle.exterior_color as string) || (apiVehicle.exterior_color as string),
      interior_color: (vehicle.interiorColor as string) || (vehicle.interior_color as string) || (apiVehicle.interior_color as string),
      doors: (vehicle.doors as number) || (apiVehicle.doors as number),
      seating_capacity: (vehicle.seating_capacity as number) || (apiVehicle.seating_capacity as number),
      features: (vehicle.features as string[]) || (apiVehicle.features as string[]) || [],
      fuel_economy: vehicle.fuel_economy ? {
        city: (vehicle.fuel_economy as Record<string, unknown>).city as number || 0,
        highway: (vehicle.fuel_economy as Record<string, unknown>).highway as number || 0,
        combined: (vehicle.fuel_economy as Record<string, unknown>).combined as number || 0,
      } : undefined,
      safety_rating: vehicle.safety_rating ? {
        overall: (vehicle.safety_rating as Record<string, unknown>).overall as number || 0,
        frontal: (vehicle.safety_rating as Record<string, unknown>).frontal as number || 0,
        side: (vehicle.safety_rating as Record<string, unknown>).side as number || 0,
        rollover: (vehicle.safety_rating as Record<string, unknown>).rollover as number || 0,
      } : undefined,
      description: (vehicle.description as string) || (apiVehicle.description as string),
      dealer_info: retailListing.dealer ? {
        name: ((retailListing.dealer as Record<string, unknown>).name as string) || 'Unknown Dealer',
        phone: (retailListing.dealer as Record<string, unknown>).phone as string,
        email: (retailListing.dealer as Record<string, unknown>).email as string,
      } : undefined,
      carfax_url: (retailListing.carfaxUrl as string) || undefined,
    };
  }
}

export const idssApiService = new IDSSApiService();
