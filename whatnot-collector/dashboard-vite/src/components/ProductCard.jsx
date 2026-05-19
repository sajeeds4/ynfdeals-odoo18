/**
 * ProductCard — reusable product display with image.
 */
export default function ProductCard({ product, size = 'md', className = '' }) {
  if (!product) return null;
  const imgSize = size === 'lg' ? 160 : size === 'sm' ? 48 : 80;

  return (
    <div className={`product-card product-card--${size} ${className}`}>
      <div className="product-card__img" style={{ width: imgSize, height: imgSize }}>
        {product.image_url ? (
          <img src={product.image_url} alt={product.product_name || 'Product'} />
        ) : (
          <div className="product-card__placeholder">
            <span>📦</span>
          </div>
        )}
      </div>
      <div className="product-card__info">
        <div className="product-card__name">{product.product_name || product.barcode || '—'}</div>
        {product.sku && <div className="product-card__sku">SKU: {product.sku}</div>}
        {product.barcode && <div className="product-card__barcode mono">{product.barcode}</div>}
        <div className="product-card__prices">
          {product.cost_price != null && (
            <span className="product-card__cost">Cost: ${Number(product.cost_price || 0).toFixed(2)}</span>
          )}
          {product.retail_price != null && (
            <span className="product-card__retail">Retail: ${Number(product.retail_price || 0).toFixed(2)}</span>
          )}
        </div>
      </div>
    </div>
  );
}
