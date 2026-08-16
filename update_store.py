import re

with open("../Jupiter_Fresh_Frontend/src/admin/Store.jsx", "r") as f:
    content = f.read()

# 1. States and openProductModal
content = content.replace(
"""  const [activeMainCategory, setActiveMainCategory] = useState(null);
  const [activeCategory, setActiveCategory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [stockFilter, setStockFilter] = useState('all');

  // Modals
  const [editingMainCategory, setEditingMainCategory] = useState(null);
  const [editingCategory, setEditingCategory] = useState(null);
  const [editingProduct, setEditingProduct] = useState(null);
  const [editingDeal, setEditingDeal] = useState(null);""",
"""  const [activeMainCategory, setActiveMainCategory] = useState(null);
  const [activeCategory, setActiveCategory] = useState(null);
  const [activeSubSubcategory, setActiveSubSubcategory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [stockFilter, setStockFilter] = useState('all');

  // Modals
  const [editingMainCategory, setEditingMainCategory] = useState(null);
  const [editingCategory, setEditingCategory] = useState(null);
  const [editingProduct, setEditingProduct] = useState(null);
  const [editingDeal, setEditingDeal] = useState(null);
  const [selectedSizes, setSelectedSizes] = useState([]);
  
  const openProductModal = (p = null) => {
    if (p) {
      setEditingProduct(p);
      setSelectedSizes(p.sizes ? p.sizes.split(',') : []);
    } else {
      setEditingProduct({ name: '', quantity: '', currentPrice: '', cutPrice: '', rating: 4.5, image: '' });
      setSelectedSizes([]);
    }
  };
  
  const toggleSize = (size) => {
    setSelectedSizes(prev => prev.includes(size) ? prev.filter(s => s !== size) : [...prev, size]);
  };""")

# 2. handleSaveCategory & handleDeleteCategory
content = content.replace(
"""  const handleSaveCategory = async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    if (!formData.get('name')) return;
    formData.append('main_category_id', activeMainCategory);

    if (editingCategory.id) {
      await fetch(`http://127.0.0.1:8000/api/categories/${editingCategory.id}`, { method: 'PUT', body: formData });
    } else {
      await fetch(`http://127.0.0.1:8000/api/categories`, { method: 'POST', body: formData });
    }
    setEditingCategory(null);
    fetchCategories();
  };

  const handleDeleteCategory = async (id) => {
    if (window.confirm("Delete this subcategory and all its products?")) {
      await fetch(`http://127.0.0.1:8000/api/categories/${id}`, { method: 'DELETE' });
      fetchCategories();
      fetchProducts();
      if (activeCategory === id) setActiveCategory(null);
    }
  };""",
"""  const handleSaveCategory = async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    if (!formData.get('name')) return;
    formData.append('main_category_id', activeMainCategory);
    
    if (editingCategory.isSubSub) {
      formData.append('parent_category_id', activeCategory);
    }

    if (editingCategory.id) {
      await fetch(`http://127.0.0.1:8000/api/categories/${editingCategory.id}`, { method: 'PUT', body: formData });
    } else {
      await fetch(`http://127.0.0.1:8000/api/categories`, { method: 'POST', body: formData });
    }
    setEditingCategory(null);
    fetchCategories();
  };

  const handleDeleteCategory = async (id, isSubSub = false) => {
    if (window.confirm("Delete this category and all its contents?")) {
      await fetch(`http://127.0.0.1:8000/api/categories/${id}`, { method: 'DELETE' });
      fetchCategories();
      fetchProducts();
      if (!isSubSub && activeCategory === id) {
        setActiveCategory(null);
        setActiveSubSubcategory(null);
      } else if (isSubSub && activeSubSubcategory === id) {
        setActiveSubSubcategory(null);
      }
    }
  };""")

# 3. handleSaveProduct
content = content.replace(
"""  const handleSaveProduct = async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const inStockVal = formData.get('in_stock') === 'on' ? 1 : 0;
    formData.set('in_stock', inStockVal);
    formData.append('category_id', activeCategory);

    if (editingProduct.id) {
      await fetch(`http://127.0.0.1:8000/api/products/${editingProduct.id}`, { method: 'PUT', body: formData });
    } else {
      await fetch(`http://127.0.0.1:8000/api/products`, { method: 'POST', body: formData });
    }
    setEditingProduct(null);
    fetchProducts();
  };""",
"""  const handleSaveProduct = async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const inStockVal = formData.get('in_stock') === 'on' ? 1 : 0;
    formData.set('in_stock', inStockVal);
    
    const targetCategoryId = activeSubSubcategory || activeCategory;
    formData.append('category_id', targetCategoryId);
    
    if (selectedSizes.length > 0) {
      formData.append('sizes', selectedSizes.join(','));
    } else {
      formData.append('sizes', '');
    }

    if (editingProduct.id) {
      await fetch(`http://127.0.0.1:8000/api/products/${editingProduct.id}`, { method: 'PUT', body: formData });
    } else {
      await fetch(`http://127.0.0.1:8000/api/products`, { method: 'POST', body: formData });
    }
    setEditingProduct(null);
    setSelectedSizes([]);
    fetchProducts();
  };""")

# 4. Filter logic
content = content.replace(
"""  let currentSubcategories = categories.filter(c => c.main_category_id === activeMainCategory);
  
  // Auto-select a subcategory if activeMainCategory changes and no subcategory is active or active belongs to another main
  useEffect(() => {
    if (activeMainCategory && activeMainCategory !== 'deals') {
      const subs = categories.filter(c => c.main_category_id === activeMainCategory);
      if (subs.length > 0 && !subs.find(c => c.id === activeCategory)) {
        setActiveCategory(subs[0].id);
      } else if (subs.length === 0) {
        setActiveCategory(null);
      }
    }
  }, [activeMainCategory, categories]);

  let currentProducts = products.filter(p => p.category_id === activeCategory);""",
"""  let currentSubcategories = categories.filter(c => c.main_category_id === activeMainCategory && !c.parent_category_id);
  let currentSubSubcategories = activeCategory ? categories.filter(c => c.parent_category_id === activeCategory) : [];
  
  useEffect(() => {
    if (activeMainCategory && activeMainCategory !== 'deals') {
      const subs = categories.filter(c => c.main_category_id === activeMainCategory && !c.parent_category_id);
      if (subs.length > 0 && !subs.find(c => c.id === activeCategory)) {
        setActiveCategory(subs[0].id);
        setActiveSubSubcategory(null);
      } else if (subs.length === 0) {
        setActiveCategory(null);
        setActiveSubSubcategory(null);
      }
    }
  }, [activeMainCategory, categories]);

  let targetCategoryId = activeSubSubcategory || activeCategory;
  let currentProducts = products.filter(p => p.category_id === targetCategoryId);""")

# 5. Open Modal buttons (replaces setEditingProduct({}))
content = content.replace("setEditingProduct({ name: '', quantity: '', currentPrice: '', cutPrice: '', rating: 4.5, image: '' })", "openProductModal(null)")
content = content.replace("setEditingProduct(p)", "openProductModal(p)")

# 6. Sidebar 2 Click (Add activeSubSubcategory clear)
content = content.replace(
"""onClick={() => setActiveCategory(c.id)}""",
"""onClick={() => { setActiveCategory(c.id); setActiveSubSubcategory(null); }}"""
)

# 7. Add Sidebar 3 dynamically
sidebar2_end = '''          </div>
        )}'''

sidebar3_html = '''

        {/* Sidebar Level 3: Sub-Subcategories */}
        {activeMainCategory !== 'deals' && activeCategory && (
          <div style={{ width: '220px', backgroundColor: 'white', padding: '16px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '15px' }}>Sub-Subcategories</h3>
              <button 
                onClick={() => setEditingCategory({ isSubSub: true })} 
                style={{ backgroundColor: '#f1f5f9', border: 'none', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '12px' }}
              >
                + Add
              </button>
            </div>
            
            {currentSubSubcategories.length === 0 ? (
              <p style={{ fontSize: '12px', color: '#64748b' }}>No sub-subcategories found.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {currentSubSubcategories.map(c => (
                  <div 
                    key={c.id} 
                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderRadius: '8px', cursor: 'pointer', backgroundColor: activeSubSubcategory === c.id ? '#eff6ff' : 'transparent', border: activeSubSubcategory === c.id ? '1px solid #bfdbfe' : '1px solid transparent' }}
                    onClick={() => setActiveSubSubcategory(c.id)}
                  >
                    <span style={{ fontWeight: activeSubSubcategory === c.id ? 'bold' : 'normal', color: activeSubSubcategory === c.id ? '#1e3a8a' : '#334155', fontSize: '14px' }}>{c.name}</span>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      <button onClick={(e) => { e.stopPropagation(); setEditingCategory({ ...c, isSubSub: true }); }} style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: '12px', color: '#3b82f6', padding: 0 }}>Edit</button>
                      <button onClick={(e) => { e.stopPropagation(); handleDeleteCategory(c.id, true); }} style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: '12px', color: '#ef4444', padding: 0 }}>Del</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}'''

content = content.replace(sidebar2_end, sidebar2_end + sidebar3_html)

# 8. Sizes selector inside Product Modal
product_modal_end = '''              <div>
                <label style={{ fontSize: '12px', color: '#64748b' }}>Product Image</label>'''

sizes_html = '''              {(() => {
                const tCat = categories.find(c => c.id === targetCategoryId);
                const tName = tCat ? tCat.name.toLowerCase() : '';
                const isTopInner = tName.includes('topwear') || tName.includes('inner wear') || tName.includes('innerwear');
                const isBottom = tName.includes('bottomwear');
                
                let availableSizes = [];
                if (isTopInner) availableSizes = ['xs', 's', 'm', 'l', 'xl', 'xxl'];
                if (isBottom) availableSizes = ['20', '22', '24', '26', '28', '30', '32', '34'];
                
                if (availableSizes.length > 0) {
                  return (
                    <div>
                      <label style={{ fontSize: '12px', color: '#64748b', display: 'block', marginBottom: '8px' }}>Available Sizes</label>
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        {availableSizes.map(sz => (
                          <div 
                            key={sz} 
                            onClick={() => toggleSize(sz)}
                            style={{ padding: '6px 12px', border: selectedSizes.includes(sz) ? '2px solid var(--primary-green)' : '1px solid #cbd5e1', borderRadius: '20px', cursor: 'pointer', fontSize: '12px', fontWeight: 'bold', backgroundColor: selectedSizes.includes(sz) ? '#f0fdf4' : 'white', color: selectedSizes.includes(sz) ? 'var(--primary-green)' : '#64748b', textTransform: 'uppercase' }}
                          >
                            {sz}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                }
                return null;
              })()}
              
              <div>
                <label style={{ fontSize: '12px', color: '#64748b' }}>Product Image</label>'''

content = content.replace(product_modal_end, sizes_html)

with open("../Jupiter_Fresh_Frontend/src/admin/Store.jsx", "w") as f:
    f.write(content)
