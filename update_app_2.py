import re

with open("../Jupiter_Fresh_Frontend/src/App.jsx", "r") as f:
    content = f.read()

# 1. Update Cart Page rendering to show size
old_cart_item = """                      <div className="cart-item-details">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <h3 className="cart-item-title">{item.name}</h3>"""

new_cart_item = """                      <div className="cart-item-details">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <h3 className="cart-item-title">{item.name} {item.selectedSize ? `(${item.selectedSize.toUpperCase()})` : ''}</h3>"""

content = content.replace(old_cart_item, new_cart_item)

# 2. Update updateCart usage in Cart Page (from item.name to item.name + size)
old_cart_item_qty = """                            <button className="cart-qty-btn" onClick={() => updateCart(item.name, -1)}>-</button>
                            <span className="cart-qty-text">{item.qty}</span>
                            <button className="cart-qty-btn" onClick={() => updateCart(item.name, 1)}>+</button>"""

new_cart_item_qty = """                            <button className="cart-qty-btn" onClick={() => updateCart(item.name, -1, item.selectedSize)}>-</button>
                            <span className="cart-qty-text">{item.qty}</span>
                            <button className="cart-qty-btn" onClick={() => updateCart(item.name, 1, item.selectedSize)}>+</button>"""

content = content.replace(old_cart_item_qty, new_cart_item_qty)

# 3. Fix Search Results Grid (`item` instead of `product`)
old_search_results_add = """                      {item.in_stock !== 0 && (
                        cart[item.name] ? (
                          <div className="quantity-control">
                            <button className="qty-btn" onClick={() => updateCart(item.name, -1)}>-</button>
                            <span className="qty-text">{cart[item.name]}</span>
                            <button className="qty-btn" onClick={() => updateCart(item.name, 1)}>+</button>
                          </div>
                        ) : (
                          <button className="add-btn" onClick={() => updateCart(item.name, 1)}>
                            <span className="plus-sign">+</span>
                          </button>
                        )
                      )}"""

new_search_results_add = """                      {item.in_stock !== 0 && (
                        item.sizes ? (
                          <div style={{ position: 'absolute', bottom: '-15px', right: '10px', display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-end' }}>
                            <select 
                              value={selectedSizes[item.id] || ''} 
                              onChange={(e) => setSelectedSizes(prev => ({...prev, [item.id]: e.target.value}))}
                              style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '11px', border: '1px solid #cbd5e1' }}
                            >
                              <option value="" disabled>Size</option>
                              {item.sizes.split(',').map(sz => <option key={sz} value={sz}>{sz.toUpperCase()}</option>)}
                            </select>
                            {cart[`${item.name}|${selectedSizes[item.id]}`] ? (
                              <div className="quantity-control">
                                <button className="qty-btn" onClick={() => updateCart(item.name, -1, selectedSizes[item.id])}>-</button>
                                <span className="qty-text">{cart[`${item.name}|${selectedSizes[item.id]}`]}</span>
                                <button className="qty-btn" onClick={() => updateCart(item.name, 1, selectedSizes[item.id])}>+</button>
                              </div>
                            ) : (
                              <button className="add-btn" onClick={() => {
                                if (!selectedSizes[item.id]) {
                                  alert("Please select a size first!");
                                  return;
                                }
                                updateCart(item.name, 1, selectedSizes[item.id]);
                              }} style={{ width: '100%', borderRadius: '4px' }}>
                                <span style={{ fontSize: '12px', fontWeight: 'bold' }}>Add</span>
                              </button>
                            )}
                          </div>
                        ) : (
                          cart[item.name] ? (
                            <div className="quantity-control">
                              <button className="qty-btn" onClick={() => updateCart(item.name, -1)}>-</button>
                              <span className="qty-text">{cart[item.name]}</span>
                              <button className="qty-btn" onClick={() => updateCart(item.name, 1)}>+</button>
                            </div>
                          ) : (
                            <button className="add-btn" onClick={() => updateCart(item.name, 1)}>
                              <span className="plus-sign">+</span>
                            </button>
                          )
                        )
                      )}"""

content = content.replace(old_search_results_add, new_search_results_add)

# 4. Remove `const qty = cart[item.name] || 0;` since it's unused now or inaccurate
content = content.replace("const qty = cart[item.name] || 0;", "")

with open("../Jupiter_Fresh_Frontend/src/App.jsx", "w") as f:
    f.write(content)
