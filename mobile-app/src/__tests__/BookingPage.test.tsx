import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import BookingPage from '../pages/BookingPage';

const { mockApiBookRide, mockGoBack, mockPush } = vi.hoisted(() => ({
  mockApiBookRide: vi.fn(),
  mockGoBack: vi.fn(),
  mockPush: vi.fn(),
}));

vi.mock('@capacitor/haptics', () => ({
  Haptics: { impact: vi.fn(), notification: vi.fn() },
  ImpactStyle: { Medium: 'medium' },
  NotificationType: { Success: 'success', Error: 'error', Warning: 'warning' },
}));

vi.mock('@capacitor/local-notifications', () => ({
  LocalNotifications: {
    checkPermissions: vi.fn().mockResolvedValue({ display: 'denied' }),
    schedule: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('../services/api', () => ({
  api: {
    bookRide: mockApiBookRide,
    cancelTrip: vi.fn().mockResolvedValue({ success: true }),
  },
}));

vi.mock('@ionic/react', async () => {
  const actual = await vi.importActual<typeof import('@ionic/react')>('@ionic/react');
  return {
    ...actual,
    useIonRouter: () => ({ goBack: mockGoBack, push: mockPush }),
  };
});

describe('BookingPage', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('gg_phone', '+254712345678');
    localStorage.setItem(
      'gg_chosen_offer',
      JSON.stringify({
        provider: 'Uber',
        ride_type: 'Uber Green',
        ev_model: 'Tesla Model 3',
        color: '#000000',
        price_kes: 1400,
        eta_min: 5,
        duration_min: 20,
        driver_name: 'James K.',
        driver_rating: 4.9,
        driver_phone: '+254712345678',
        plate: 'KDA 123 A',
        distance_km: 9.2,
        co2_saved_g: 1100,
      }),
    );
    localStorage.setItem('gg_pickup', 'Westlands');
    localStorage.setItem('gg_dest', 'Mombasa Road');
    mockApiBookRide.mockReset();
    mockApiBookRide.mockResolvedValue({
      success: true,
      trip_id: 'GG-123456',
      request_id: 'req-1',
      status: 'processing',
      customer_msg: 'Booking confirmed',
      driver_name: 'James K.',
      driver_phone: '+254712345678',
      plate: 'KDA 123 A',
      ev_model: 'Tesla Model 3',
      carbon_result: {
        distance_km: 9.2,
        baseline_emissions_kg: 1.2,
        project_emissions_kg: 0.3,
        net_reduction_kg: 1.0,
        net_vcu: 0.0008,
        vcu_value_kes: 1.3,
        trees_equivalent: 0.036,
        petrol_saved_litres: 0.12,
        methodology: 'Verra VM0038 v1.0',
      },
    });
  });

  it('renders the booking summary and submits the booking form', async () => {
    render(<BookingPage />);

    expect(screen.getByText('Confirm Ride')).toBeInTheDocument();
    expect(screen.getByText('Westlands')).toBeInTheDocument();
    expect(screen.getByText('Mombasa Road')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /confirm & pay with m-pesa/i }));

    await waitFor(() => expect(mockApiBookRide).toHaveBeenCalledTimes(1));
    expect(mockApiBookRide).toHaveBeenCalledWith('+254712345678', 'Uber', expect.objectContaining({ provider: 'Uber' }));
    expect(await screen.findByText(/booking confirmed/i)).toBeInTheDocument();
  });
});
