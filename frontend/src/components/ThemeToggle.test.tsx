import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeToggle, useTheme } from './ThemeToggle';

function Harness() {
  const { theme, toggleTheme } = useTheme();
  return <><span data-testid="theme">{theme}</span><ThemeToggle theme={theme} onToggle={toggleTheme} /></>;
}

beforeEach(() => { localStorage.clear(); document.documentElement.removeAttribute('data-theme'); });
afterEach(() => cleanup());

describe('theme preference', () => {
  it('defaults to light and toggles/persists only the theme value', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getByTestId('theme')).toHaveTextContent('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    const toggle = screen.getByRole('button', { name: 'Switch to dark theme' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await user.click(toggle);
    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(localStorage.getItem('tryedveo-theme')).toBe('dark');
    expect(localStorage.length).toBe(1);
    await user.click(screen.getByRole('button', { name: 'Switch to light theme' }));
    expect(localStorage.getItem('tryedveo-theme')).toBe('light');
  });

  it('restores a valid dark preference and ignores invalid values', () => {
    localStorage.setItem('tryedveo-theme', 'dark');
    const { unmount } = render(<Harness />);
    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toHaveAttribute('aria-pressed', 'true');
    unmount();
    localStorage.setItem('tryedveo-theme', 'sepia');
    render(<Harness />);
    expect(screen.getByTestId('theme')).toHaveTextContent('light');
  });

  it('uses keyboard activation', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    screen.getByRole('button', { name: 'Switch to dark theme' }).focus();
    await user.keyboard('{Enter}');
    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
  });
});
