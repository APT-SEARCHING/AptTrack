import { medianApartmentPrice } from './medianPrice';

const apt = (min: number | null, max: number | null) => ({ min_price: min, max_price: max });

describe('medianApartmentPrice', () => {
  test('odd count — returns middle midpoint', () => {
    // midpoints: 1000, 2000, 3000, 4000, 5000 → median = 3000
    const apts = [
      apt(800,  1200),  // mid 1000
      apt(1800, 2200),  // mid 2000
      apt(2800, 3200),  // mid 3000
      apt(3800, 4200),  // mid 4000
      apt(4800, 5200),  // mid 5000
    ];
    expect(medianApartmentPrice(apts)).toBe(3000);
  });

  test('even count — averages the two middle midpoints', () => {
    // midpoints: 1000, 2000, 3000, 4000 → median = (2000+3000)/2 = 2500
    const apts = [
      apt(800,  1200),
      apt(1800, 2200),
      apt(2800, 3200),
      apt(3800, 4200),
    ];
    expect(medianApartmentPrice(apts)).toBe(2500);
  });

  test('skewed range does not pull median — unlike avg of all prices', () => {
    // Without midpoint: prices = [1000,1000, 1000,1000, 1000,9000]
    //   flatMap avg = (1000*4 + 1000 + 9000) / 6 = 14000/6 ≈ 2333  (wrong)
    // With midpoints: [1000, 1000, 5000] → median = 1000  (correct)
    const apts = [
      apt(1000, 1000),
      apt(1000, 1000),
      apt(1000, 9000),  // wide range outlier
    ];
    expect(medianApartmentPrice(apts)).toBe(1000);
  });

  test('null prices excluded from calculation', () => {
    // Only two valid apts; null-price apt ignored
    const apts = [
      apt(1000, 2000),  // mid 1500
      apt(3000, 4000),  // mid 3500
      apt(null, null),
    ];
    expect(medianApartmentPrice(apts)).toBe(2500); // (1500+3500)/2
  });

  test('all null prices returns 0', () => {
    expect(medianApartmentPrice([apt(null, null), apt(null, 2000)])).toBe(0);
  });

  test('empty array returns 0', () => {
    expect(medianApartmentPrice([])).toBe(0);
  });
});
