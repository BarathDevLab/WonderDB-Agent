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

export const downloadSvgAsPng = async (source: SVGSVGElement, title: string) => {
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

  const svgBlob = new Blob([new XMLSerializer().serializeToString(clone)], {
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
    triggerDownload(canvas.toDataURL('image/png'), `${safeFilename(title)}.png`);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
};
