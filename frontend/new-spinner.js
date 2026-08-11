/* ==========================================================================
   NewSpinner Web Component (<new-spinner>)
   Self-contained canvas component for the new video animation
   ========================================================================== */

class NewSpinner extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: inline-block;
          width: var(--ball-size, 24px);
          height: var(--ball-size, 24px);
          position: relative;
          vertical-align: middle;
        }

        .spinner-container {
          width: 100%;
          height: 100%;
          border-radius: 50%;
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #000000;
          box-shadow: 0 0 6px rgba(74, 222, 128, 0.2);
          transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.3s ease, opacity 0.3s ease;
          opacity: 0.75;
          overflow: hidden;
        }

        .spinner-container.spinning {
          transform: scale(1.1);
          box-shadow: 0 0 12px rgba(74, 222, 128, 0.6), 0 0 20px rgba(74, 222, 128, 0.3);
          opacity: 1;
        }

        .spinner-container.spinning::after {
          content: '';
          position: absolute;
          inset: -1px;
          border-radius: 50%;
          border: 1px solid rgba(74, 222, 128, 0.7);
          animation: pulseGlow 1.8s infinite ease-in-out;
          pointer-events: none;
        }

        @keyframes pulseGlow {
          0% { transform: scale(1); opacity: 0.9; }
          50% { transform: scale(1.25); opacity: 0; }
          100% { transform: scale(1); opacity: 0.9; }
        }

        canvas {
          width: 100%;
          height: 100%;
          border-radius: 50%;
          display: block;
          mix-blend-mode: screen;
        }
      </style>

      <div class="spinner-container" id="container">
        <canvas id="canvas" width="64" height="64"></canvas>
      </div>
    `;

    this.canvas = this.shadowRoot.getElementById('canvas');
    this.ctx = this.canvas.getContext('2d');
    this.container = this.shadowRoot.getElementById('container');

    this.currentFrame = 5;
    this.numFrames = 249;
    this.frameWidth = 64;
    this.frameHeight = 64;
    this.fps = 30;
    this.isSpinning = false;
    this.animId = null;
    this.lastTime = 0;
    this.speed = 1.0;

    // Sprite sheet image asset
    this.sprite = new Image();
    this.sprite.src = 'new_spritesheet.png';
    this.sprite.onload = () => {
      this.renderFrame(this.currentFrame);
    };
  }

  static get observedAttributes() {
    return ['spinning', 'size', 'speed'];
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (name === 'spinning') {
      if (newValue !== null && newValue !== 'false') {
        this.start();
      } else {
        this.stop();
      }
    }
    if (name === 'size') {
      this.style.setProperty('--ball-size', `${newValue}px`);
    }
    if (name === 'speed') {
      this.speed = parseFloat(newValue) || 1.0;
    }
  }

  connectedCallback() {
    const size = this.getAttribute('size') || '24';
    this.style.setProperty('--ball-size', `${size}px`);
    
    if (this.hasAttribute('spinning')) {
      this.start();
    } else {
      this.renderFrame(this.currentFrame);
    }
  }

  disconnectedCallback() {
    this.stop();
  }

  start() {
    if (this.isSpinning) return;
    this.isSpinning = true;
    this.setAttribute('spinning', 'true');
    this.container.classList.add('spinning');
    this.lastTime = performance.now();
    this.loop(performance.now());
  }

  stop() {
    this.isSpinning = false;
    this.removeAttribute('spinning');
    this.container.classList.remove('spinning');
    if (this.animId) {
      cancelAnimationFrame(this.animId);
      this.animId = null;
    }
    // Maintain currentFrame so it pauses gracefully
  }

  setSpeed(s) {
    this.speed = s;
    this.setAttribute('speed', s);
  }

  loop(now) {
    if (!this.isSpinning) return;
    
    const delta = (now - this.lastTime) / 1000;
    const interval = 1 / (this.fps * this.speed);

    if (delta >= interval) {
      this.currentFrame = (this.currentFrame + 1) % this.numFrames;
      this.renderFrame(this.currentFrame);
      this.lastTime = now - (delta % interval);
    }

    this.animId = requestAnimationFrame(this.loop.bind(this));
  }

  renderFrame(frameIndex) {
    this.ctx.clearRect(0, 0, this.frameWidth, this.frameHeight);
    if (this.sprite.complete && this.sprite.naturalWidth > 0) {
      this.ctx.drawImage(
        this.sprite,
        frameIndex * this.frameWidth, 0,
        this.frameWidth, this.frameHeight,
        0, 0,
        this.frameWidth, this.frameHeight
      );
    } else {
      this.renderProceduralSphere(frameIndex);
    }
  }

  renderProceduralSphere(frameIndex) {
    const ctx = this.ctx;
    const cx = 32, cy = 32, r = 28;
    ctx.clearRect(0, 0, 64, 64);

    const grad = ctx.createRadialGradient(cx - 8, cy - 8, 4, cx, cy, r);
    grad.addColorStop(0, '#86efac');
    grad.addColorStop(0.5, '#22c55e');
    grad.addColorStop(1, '#052e16');

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.lineWidth = 1.5;
    const angle = (frameIndex / this.numFrames) * Math.PI * 2;
    for (let i = -r + 4; i < r; i += 8) {
      const w = Math.sqrt(r * r - i * i);
      ctx.beginPath();
      ctx.ellipse(cx, cy + i * 0.5, w, 4, angle, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
}

customElements.define('new-spinner', NewSpinner);
