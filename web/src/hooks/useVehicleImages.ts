import { useState, useEffect } from 'react';

interface VehicleImage {
  url: string;
  title?: string;
  caption?: string;
}

interface VehicleImagesResponse {
  images: VehicleImage[];
  count?: number;
  error?: string;
  message?: string;
}

export function useVehicleImages(vin?: string) {
  const [images, setImages] = useState<VehicleImage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!vin) {
      setImages([]);
      setError(null);
      return;
    }

    const fetchImages = async () => {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(`/api/vehicle-images?vin=${vin}`);
        const data: VehicleImagesResponse = await response.json();

        if (data.error) {
          setError(data.error);
          setImages([]);
        } else {
          setImages(data.images || []);
        }
      } catch (err) {
        setError('Failed to fetch vehicle images');
        setImages([]);
      } finally {
        setLoading(false);
      }
    };

    fetchImages();
  }, [vin]);

  return { images, loading, error };
}
