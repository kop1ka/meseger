# Frontend Structure Documentation

## File Organization

```
/workspace/
├── index.html          # Main HTML entry point
├── css/
│   └── styles.css      # All CSS styles with responsive design
├── js/
│   └── app.js          # JavaScript application logic
└── assets/
    └── favicon.svg     # SVG favicon
```

## Technologies Used

### CSS Features
- **CSS Variables** - Easy theming and color management
- **Mobile-First Responsive Design** - Optimized for all screen sizes
- **Media Queries** - Breakpoints at 480px, 768px, 1024px
- **Dark Mode Support** - Automatic theme switching
- **Reduced Motion** - Accessibility support
- **Smooth Animations** - Fade-in effects and transitions
- **Touch Optimizations** - iOS zoom prevention, touch feedback

### JavaScript Features
- **ES6+ Class-based Architecture** - Clean, maintainable code
- **Event Delegation** - Efficient event handling
- **WebSocket Management** - Auto-reconnection with exponential backoff
- **Mobile Optimizations**:
  - Touch feedback on buttons
  - Viewport height fixing for mobile browsers
  - Auto-resize text input
  - Online/offline detection
  - Visibility change handling
- **Custom Alerts** - Non-blocking notification system
- **XSS Protection** - HTML escaping for user input

## Mobile Adaptations

### Viewport Meta Tags
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="theme-color" content="#667eea">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
```

### Responsive Breakpoints
- **Mobile (≤480px)**: Full-screen layout, larger touch targets
- **Tablet (481-768px)**: Adjusted spacing and font sizes
- **iPad/Small Desktop (769-1024px)**: 85% width container
- **Desktop (≥1025px)**: Maximum 900px container

### iOS-Specific Optimizations
- 16px font size on inputs prevents auto-zoom
- Touch event handlers for visual feedback
- `user-scalable=no` prevents accidental zooming
- Web app capable meta tags for home screen installation

### Performance Optimizations
- External CSS/JS files for browser caching
- `defer` attribute on scripts for non-blocking load
- SVG favicon for crisp display on all devices
- CSS containment and will-use properties
- Smooth scrolling with native momentum on iOS

## Browser Support
- Modern browsers (Chrome, Firefox, Safari, Edge)
- iOS Safari 12+
- Android Chrome 80+
- Graceful degradation for older browsers

## Usage

Simply open `index.html` in a browser or serve it with the Python server:

```bash
python server.py
```

Then navigate to `http://localhost:8000` (or the appropriate port).
