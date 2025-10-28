interface LogEventRequest {
  event_type: string;
  data: Record<string, any>;
  timestamp?: string;
}

interface LogEventResponse {
  status: string;
  event_id: number;
  timestamp: string;
}

export class LoggingService {
  private static baseUrl = process.env.NODE_ENV === 'production' 
    ? 'https://your-api-domain.com' 
    : 'http://localhost:8000';

  /**
   * Log a user interaction event
   */
  static async logEvent(sessionId: string, eventType: string, data: Record<string, any> = {}): Promise<LogEventResponse> {
    const request: LogEventRequest = {
      event_type: eventType,
      data,
      timestamp: new Date().toISOString()
    };

    try {
      const response = await fetch(`${this.baseUrl}/session/${sessionId}/event`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Failed to log event:', error);
      throw error;
    }
  }

  /**
   * Log when user views vehicle details
   */
  static async logVehicleView(sessionId: string, vehicleId: string, vin?: string): Promise<void> {
    try {
      await this.logEvent(sessionId, 'vehicle_view', {
        vehicle_id: vehicleId,
        vin: vin || 'unknown',
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Failed to log vehicle view:', error);
    }
  }

  /**
   * Log when user clicks on a vehicle
   */
  static async logVehicleClick(sessionId: string, vehicleId: string, vin?: string): Promise<void> {
    try {
      await this.logEvent(sessionId, 'vehicle_click', {
        vehicle_id: vehicleId,
        vin: vin || 'unknown',
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Failed to log vehicle click:', error);
    }
  }

  /**
   * Log when user views vehicle photos
   */
  static async logPhotoView(sessionId: string, vehicleId: string, vin?: string): Promise<void> {
    try {
      await this.logEvent(sessionId, 'photo_view', {
        vehicle_id: vehicleId,
        vin: vin || 'unknown',
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Failed to log photo view:', error);
    }
  }

  /**
   * Log when user favorites/unfavorites a vehicle
   */
  static async logFavoriteToggle(sessionId: string, vehicleId: string, vin: string, isFavorite: boolean): Promise<void> {
    try {
      await this.logEvent(sessionId, isFavorite ? 'vehicle_favorited' : 'vehicle_unfavorited', {
        vehicle_id: vehicleId,
        vin: vin || 'unknown',
        action: isFavorite ? 'favorited' : 'unfavorited',
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error('Failed to log favorite toggle:', error);
    }
  }

  /**
   * Log custom events
   */
  static async logCustomEvent(sessionId: string, eventType: string, data: Record<string, any> = {}): Promise<void> {
    try {
      await this.logEvent(sessionId, eventType, data);
    } catch (error) {
      console.error('Failed to log custom event:', error);
    }
  }
}
