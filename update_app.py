import re

with open("../Jupiter_Fresh_Frontend/src/App.jsx", "r") as f:
    content = f.read()

# 1. State for selected product sizes (temporary UI state)
content = content.replace(
"""  const [cart, setCart] = useLocalStorage('cart', {});""",
"""  const [cart, setCart] = useLocalStorage('cart', {});
  const [selectedSizes, setSelectedSizes] = useState({});"""
)

# 2. Add activeSubSubcategory state
content = content.replace(
"""  const [categoryTabActiveCategory, setCategoryTabActiveCategory] = useLocalStorage('categoryTabActiveCategory', 'Veggies');""",
"""  const [categoryTabActiveCategory, setCategoryTabActiveCategory] = useLocalStorage('categoryTabActiveCategory', 'Veggies');
  const [categoryTabActiveSubSub, setCategoryTabActiveSubSub] = useLocalStorage('categoryTabActiveSubSub', '');"""
)

# 3. Fix categoryTabVisibleSubcategories
content = content.replace(
"""  const categoryTabVisibleSubcategories = React.useMemo(() => {
    if (!categoryTabMainCatObj) return categoryList;
    return categoryList.filter(c => c.main_category_id === categoryTabMainCatObj.id);
  }, [categoryList, categoryTabMainCatObj]);""",
"""  const categoryTabVisibleSubcategories = React.useMemo(() => {
    if (!categoryTabMainCatObj) return categoryList.filter(c => !c.parent_category_id);
    return categoryList.filter(c => c.main_category_id === categoryTabMainCatObj.id && !c.parent_category_id);
  }, [categoryList, categoryTabMainCatObj]);
  
  const categoryTabActiveCatObj = React.useMemo(() => {
    return categoryList.find(c => c.name === categoryTabActiveCategory);
  }, [categoryList, categoryTabActiveCategory]);

  const categoryTabVisibleSubSubcategories = React.useMemo(() => {
    if (!categoryTabActiveCatObj) return [];
    return categoryList.filter(c => c.parent_category_id === categoryTabActiveCatObj.id);
  }, [categoryList, categoryTabActiveCatObj]);"""
)

# 4. Auto-select activeSubSubcategory
content = content.replace(
"""  React.useEffect(() => {
    if (categoryTabVisibleSubcategories.length > 0) {
      const isValid = categoryTabVisibleSubcategories.some(s => s.name === categoryTabActiveCategory);
      if (!isValid) {
        setCategoryTabActiveCategory(categoryTabVisibleSubcategories[0].name);
      }
    } else {
      setCategoryTabActiveCategory('');
    }
  }, [categoryTabVisibleSubcategories]);""",
"""  React.useEffect(() => {
    if (categoryTabVisibleSubcategories.length > 0) {
      const isValid = categoryTabVisibleSubcategories.some(s => s.name === categoryTabActiveCategory);
      if (!isValid) {
        setCategoryTabActiveCategory(categoryTabVisibleSubcategories[0].name);
      }
    } else {
      setCategoryTabActiveCategory('');
    }
  }, [categoryTabVisibleSubcategories]);
  
  React.useEffect(() => {
    if (categoryTabVisibleSubSubcategories.length > 0) {
      const isValid = categoryTabVisibleSubSubcategories.some(s => s.name === categoryTabActiveSubSub);
      if (!isValid) {
        setCategoryTabActiveSubSub(categoryTabVisibleSubSubcategories[0].name);
      }
    } else {
      setCategoryTabActiveSubSub('');
    }
  }, [categoryTabVisibleSubSubcategories]);"""
)

# 5. Fix updateCart function to accept size
content = content.replace(
"""  const updateCart = (productName, delta) => {
    setCart(prev => {
      const currentQty = prev[productName] || 0;
      const newQty = currentQty + delta;
      const newCart = { ...prev };
      if (newQty <= 0) {
        delete newCart[productName];
      } else {
        newCart[productName] = newQty;
      }
      return newCart;
    });
  };""",
"""  const updateCart = (productName, delta, size = null) => {
    const cartKey = size ? `${productName}|${size}` : productName;
    setCart(prev => {
      const currentQty = prev[cartKey] || 0;
      const newQty = currentQty + delta;
      const newCart = { ...prev };
      if (newQty <= 0) {
        delete newCart[cartKey];
      } else {
        newCart[cartKey] = newQty;
      }
      return newCart;
    });
  };"""
)

# 6. Fix cartDetails computation
content = content.replace(
"""    Object.entries(cart).forEach(([name, qty]) => {
      const product = allProducts.find(p => p.name === name);
      if (product) {
        items.push({ ...product, qty });
        itemTotal += product.currentPrice * qty;
      }
    });""",
"""    Object.entries(cart).forEach(([cartKey, qty]) => {
      const [name, size] = cartKey.split('|');
      const product = allProducts.find(p => p.name === name);
      if (product) {
        items.push({ ...product, qty, selectedSize: size });
        itemTotal += product.currentPrice * qty;
      }
    });"""
)

# 7. Add horizontal panel for sub-subcategories and fix product grid
content = content.replace(
"""                <div className="product-grid" style={{ paddingTop: '12px' }}>
                  {(categoryData[categoryTabActiveCategory] || []).map((product, idx) => (""",
"""                {/* Horizontal Sub-Subcategories Panel */}
                {categoryTabVisibleSubSubcategories.length > 0 && (
                  <div style={{
                    display: 'flex',
                    overflowX: 'auto',
                    gap: '8px',
                    padding: '8px 16px',
                    backgroundColor: 'var(--white)',
                    borderBottom: '1px solid #f1f5f9',
                    scrollbarWidth: 'none',
                    msOverflowStyle: 'none',
                    flexShrink: 0
                  }}>
                    {categoryTabVisibleSubSubcategories.map((ssc, idx) => (
                      <button
                        key={idx}
                        onClick={() => setCategoryTabActiveSubSub(ssc.name)}
                        style={{
                          padding: '6px 12px',
                          borderRadius: '16px',
                          border: categoryTabActiveSubSub === ssc.name ? '1px solid transparent' : '1px solid #e2e8f0',
                          fontSize: '13px',
                          fontWeight: '600',
                          backgroundColor: categoryTabActiveSubSub === ssc.name ? '#0271b9' : '#ffffff',
                          color: categoryTabActiveSubSub === ssc.name ? 'var(--white)' : '#64748b',
                          cursor: 'pointer',
                          transition: 'all 0.2s ease'
                        }}
                      >
                        {ssc.name}
                      </button>
                    ))}
                  </div>
                )}

                <div className="product-grid" style={{ paddingTop: '12px' }}>
                  {(categoryData[categoryTabVisibleSubSubcategories.length > 0 ? categoryTabActiveSubSub : categoryTabActiveCategory] || []).map((product, idx) => ("""
)

# 8. Add size selector to Category Tab Product Card
old_category_product_add = """                        {product.in_stock !== 0 && (
                          cart[product.name] ? (
                            <div className="quantity-control">
                              <button className="qty-btn" onClick={() => updateCart(product.name, -1)}>-</button>
                              <span className="qty-text">{cart[product.name]}</span>
                              <button className="qty-btn" onClick={() => updateCart(product.name, 1)}>+</button>
                            </div>
                          ) : (
                            <button className="add-btn" onClick={() => updateCart(product.name, 1)}>
                              <span className="plus-sign">+</span>
                            </button>
                          )
                        )}"""

new_category_product_add = """                        {product.in_stock !== 0 && (
                          product.sizes ? (
                            <div style={{ position: 'absolute', bottom: '-15px', right: '10px', display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-end' }}>
                              <select 
                                value={selectedSizes[product.id] || ''} 
                                onChange={(e) => setSelectedSizes(prev => ({...prev, [product.id]: e.target.value}))}
                                style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '11px', border: '1px solid #cbd5e1' }}
                              >
                                <option value="" disabled>Size</option>
                                {product.sizes.split(',').map(sz => <option key={sz} value={sz}>{sz.toUpperCase()}</option>)}
                              </select>
                              {cart[`${product.name}|${selectedSizes[product.id]}`] ? (
                                <div className="quantity-control">
                                  <button className="qty-btn" onClick={() => updateCart(product.name, -1, selectedSizes[product.id])}>-</button>
                                  <span className="qty-text">{cart[`${product.name}|${selectedSizes[product.id]}`]}</span>
                                  <button className="qty-btn" onClick={() => updateCart(product.name, 1, selectedSizes[product.id])}>+</button>
                                </div>
                              ) : (
                                <button className="add-btn" onClick={() => {
                                  if (!selectedSizes[product.id]) {
                                    alert("Please select a size first!");
                                    return;
                                  }
                                  updateCart(product.name, 1, selectedSizes[product.id]);
                                }} style={{ width: '100%', borderRadius: '4px' }}>
                                  <span style={{ fontSize: '12px', fontWeight: 'bold' }}>Add</span>
                                </button>
                              )}
                            </div>
                          ) : (
                            cart[product.name] ? (
                              <div className="quantity-control">
                                <button className="qty-btn" onClick={() => updateCart(product.name, -1)}>-</button>
                                <span className="qty-text">{cart[product.name]}</span>
                                <button className="qty-btn" onClick={() => updateCart(product.name, 1)}>+</button>
                              </div>
                            ) : (
                              <button className="add-btn" onClick={() => updateCart(product.name, 1)}>
                                <span className="plus-sign">+</span>
                              </button>
                            )
                          )
                        )}"""

content = content.replace(old_category_product_add, new_category_product_add)

# 9. Fix empty state fallback for category tab
content = content.replace(
"""                {!(categoryData[categoryTabActiveCategory] || []).length && (
                  <p style={{ textAlign: 'center', marginTop: '40px', color: '#64748b', fontSize: '14px' }}>No products found.</p>
                )}""",
"""                {!(categoryData[categoryTabVisibleSubSubcategories.length > 0 ? categoryTabActiveSubSub : categoryTabActiveCategory] || []).length && (
                  <p style={{ textAlign: 'center', marginTop: '40px', color: '#64748b', fontSize: '14px' }}>No products found.</p>
                )}"""
)


with open("../Jupiter_Fresh_Frontend/src/App.jsx", "w") as f:
    f.write(content)
