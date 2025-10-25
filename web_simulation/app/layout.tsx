import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Simulator Demo',
  description: 'Autonomous user simulation playback for the car recommendation assistant.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
