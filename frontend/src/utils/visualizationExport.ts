const safeFilename = (title: string) =>
  title
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') || 'visualization';

const triggerDownload = (url: string, filename: string) => {
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
};

const triggerBlobDownload = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  triggerDownload(url, filename);
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
};

const nodeTextWithBreaks = (node: Node): string => {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent || '';
  if (node instanceof Element && node.tagName.toLowerCase() === 'br') return '\n';
  return Array.from(node.childNodes).map(nodeTextWithBreaks).join('');
};

const replaceHtmlLabelsWithSvgText = (svg: SVGSVGElement) => {
  const numericAttribute = (element: Element, name: string) => {
    const value = Number.parseFloat(element.getAttribute(name) || '0');
    return Number.isFinite(value) ? value : 0;
  };

  svg.querySelectorAll('foreignObject').forEach((foreignObject) => {
    const lines = nodeTextWithBreaks(foreignObject)
      .split('\n')
      .map((line) => line.replace(/\s+/g, ' ').trim())
      .filter(Boolean);
    const x = numericAttribute(foreignObject, 'x');
    const y = numericAttribute(foreignObject, 'y');
    const width = numericAttribute(foreignObject, 'width');
    const height = numericAttribute(foreignObject, 'height');
    const centerX = x + width / 2;
    const centerY = y + height / 2;
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', String(centerX));
    text.setAttribute('y', String(centerY));
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dominant-baseline', 'middle');
    text.setAttribute('fill', '#f4f4f5');
    text.setAttribute('font-family', 'ui-sans-serif, system-ui, sans-serif');
    text.setAttribute('font-size', '14');

    (lines.length ? lines : ['']).forEach((line, index, allLines) => {
      const tspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
      tspan.setAttribute('x', String(centerX));
      tspan.setAttribute('dy', index === 0 ? `${-(allLines.length - 1) * 0.6}em` : '1.2em');
      tspan.textContent = line;
      text.appendChild(tspan);
    });
    foreignObject.replaceWith(text);
  });
};

export const downloadCanvasAsPng = (source: HTMLCanvasElement, title: string) => {
  const canvas = document.createElement('canvas');
  canvas.width = source.width;
  canvas.height = source.height;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas export is not supported by this browser.');
  context.fillStyle = '#1e1f20';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(source, 0, 0);
  triggerDownload(canvas.toDataURL('image/png'), `${safeFilename(title)}.png`);
};

export const downloadSvgAsPng = async (
  source: SVGSVGElement,
  title: string,
): Promise<'png' | 'svg'> => {
  const clone = source.cloneNode(true) as SVGSVGElement;
  const viewBox = source.viewBox.baseVal;
  const bounds = source.getBoundingClientRect();
  const width = viewBox?.width || bounds.width || 1200;
  const height = viewBox?.height || bounds.height || 800;
  const scale = Math.min(2, 8192 / Math.max(width, height));
  const exportWidth = Math.max(1, Math.round(width * scale));
  const exportHeight = Math.max(1, Math.round(height * scale));

  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('width', String(width));
  clone.setAttribute('height', String(height));
  clone.style.maxWidth = 'none';
  replaceHtmlLabelsWithSvgText(clone);

  const serializedSvg = new XMLSerializer().serializeToString(clone);
  const svgBlob = new Blob([serializedSvg], {
    type: 'image/svg+xml;charset=utf-8',
  });
  const objectUrl = URL.createObjectURL(svgBlob);

  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error('The rendered diagram could not be converted to an image.'));
      image.src = objectUrl;
    });

    const canvas = document.createElement('canvas');
    canvas.width = exportWidth;
    canvas.height = exportHeight;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Canvas export is not supported by this browser.');
    context.fillStyle = '#1e1f20';
    context.fillRect(0, 0, exportWidth, exportHeight);
    context.drawImage(image, 0, 0, exportWidth, exportHeight);
    const pngBlob = await new Promise<Blob>((resolve, reject) => {
      try {
        canvas.toBlob(
          (blob) => blob ? resolve(blob) : reject(new Error('PNG encoder returned no data.')),
          'image/png',
        );
      } catch (error) {
        reject(error);
      }
    });
    triggerBlobDownload(pngBlob, `${safeFilename(title)}.png`);
    return 'png';
  } catch (error) {
    // Some browsers prohibit rasterizing SVG features even after HTML labels
    // are normalized. SVG is still a rendered image and remains fully scalable.
    console.warn('PNG diagram export failed; downloading SVG fallback.', error);
    triggerBlobDownload(svgBlob, `${safeFilename(title)}.svg`);
    return 'svg';
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
};
