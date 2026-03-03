// ─── Sidebar Toggle (Mobile) ───
document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.querySelector('.mobile-toggle');
    const sidebar = document.querySelector('.sidebar');
    if (toggle && sidebar) {
        toggle.addEventListener('click', () => sidebar.classList.toggle('open'));
        document.querySelector('.main')?.addEventListener('click', () => sidebar.classList.remove('open'));
    }

    // Auto-dismiss flash messages
    document.querySelectorAll('.flash').forEach(el => {
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(-10px)';
            setTimeout(() => el.remove(), 300);
        }, 5000);
    });

    // Character counter
    initCharCounter();

    // Paid article toggle
    initPaidToggle();

    // Cover image preview
    initImageUpload();
});

// ─── Character Counter ───
function initCharCounter() {
    const body = document.getElementById('article-body');
    const counter = document.getElementById('char-counter');
    const minChars = parseInt(document.getElementById('min-chars')?.value || '0');
    const maxChars = parseInt(document.getElementById('max-chars')?.value || '99999');

    if (!body || !counter) return;

    function update() {
        const len = body.value.length;
        counter.textContent = `${len.toLocaleString()} 文字`;

        counter.className = 'char-counter';
        if (len < minChars) {
            counter.classList.add('warn');
            counter.textContent += ` (最小 ${minChars.toLocaleString()} 文字)`;
        } else if (len > maxChars) {
            counter.classList.add('error');
            counter.textContent += ` (最大 ${maxChars.toLocaleString()} 文字超過)`;
        } else {
            counter.classList.add('ok');
        }
    }

    body.addEventListener('input', update);
    update();
}

// ─── Paid Article Toggle ───
function initPaidToggle() {
    const toggle = document.getElementById('is-paid');
    const paidSection = document.getElementById('paid-settings');
    if (!toggle || !paidSection) return;

    function update() {
        paidSection.style.display = toggle.checked ? 'block' : 'none';
    }
    toggle.addEventListener('change', update);
    update();
}

// ─── Image Upload Preview ───
function initImageUpload() {
    // Cover image
    const coverInput = document.getElementById('cover-image-input');
    const coverZone = document.getElementById('cover-upload-zone');
    if (coverInput && coverZone) {
        coverZone.addEventListener('click', () => coverInput.click());
        coverInput.addEventListener('change', () => {
            if (coverInput.files && coverInput.files[0]) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    coverZone.innerHTML = `<img src="${e.target.result}" alt="表紙">`;
                    coverZone.classList.add('has-image');
                };
                reader.readAsDataURL(coverInput.files[0]);
            }
        });

        // Drag & drop
        coverZone.addEventListener('dragover', (e) => { e.preventDefault(); coverZone.style.borderColor = 'var(--primary)'; });
        coverZone.addEventListener('dragleave', () => { coverZone.style.borderColor = ''; });
        coverZone.addEventListener('drop', (e) => {
            e.preventDefault();
            coverZone.style.borderColor = '';
            if (e.dataTransfer.files.length) {
                coverInput.files = e.dataTransfer.files;
                coverInput.dispatchEvent(new Event('change'));
            }
        });
    }

    // Article images
    const imgInput = document.getElementById('article-images-input');
    const imgZone = document.getElementById('article-images-zone');
    const imgList = document.getElementById('article-images-list');
    if (imgInput && imgZone) {
        imgZone.addEventListener('click', () => imgInput.click());
        imgInput.addEventListener('change', () => {
            if (!imgList) return;
            imgList.innerHTML = '';
            Array.from(imgInput.files).forEach(file => {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const div = document.createElement('div');
                    div.className = 'image-preview-item';
                    div.innerHTML = `<img src="${e.target.result}" alt="${file.name}">`;
                    imgList.appendChild(div);
                };
                reader.readAsDataURL(file);
            });
        });
    }
}

// ─── Modal ───
function openModal(id) {
    document.getElementById(id)?.classList.add('show');
}

function closeModal(id) {
    document.getElementById(id)?.classList.remove('show');
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('show');
    }
});

// ─── Confirm Delete ───
function confirmDelete(formId, name) {
    if (confirm(`「${name}」を削除しますか？この操作は取り消せません。`)) {
        document.getElementById(formId).submit();
    }
}

// ─── Account settings: load defaults when account is selected ───
function onAccountChange(select) {
    const option = select.options[select.selectedIndex];
    if (!option) return;

    const tags = option.dataset.tags || '';
    const price = option.dataset.price || '0';
    const minCharsVal = option.dataset.minChars || '1000';
    const maxCharsVal = option.dataset.maxChars || '5000';

    const tagsInput = document.getElementById('article-tags');
    const priceInput = document.getElementById('article-price');
    const minCharsInput = document.getElementById('min-chars');
    const maxCharsInput = document.getElementById('max-chars');

    if (tagsInput && !tagsInput.value) tagsInput.value = tags;
    if (priceInput && priceInput.value === '0') priceInput.value = price;
    if (minCharsInput) { minCharsInput.value = minCharsVal; }
    if (maxCharsInput) { maxCharsInput.value = maxCharsVal; }

    // Re-init char counter with new limits
    initCharCounter();
}

// ─── Auto refresh stats (dashboard) ───
function refreshStats() {
    fetch('/api/stats')
        .then(r => r.json())
        .then(data => {
            const el = (id) => document.getElementById(id);
            if (el('stat-accounts')) el('stat-accounts').textContent = data.total_accounts;
            if (el('stat-articles')) el('stat-articles').textContent = data.total_articles;
            if (el('stat-published')) el('stat-published').textContent = data.published;
            if (el('stat-scheduled')) el('stat-scheduled').textContent = data.scheduled;
            if (el('stat-drafts')) el('stat-drafts').textContent = data.draft;
        })
        .catch(() => {});
}

// Refresh stats every 30 seconds on dashboard
if (document.getElementById('stat-accounts')) {
    setInterval(refreshStats, 30000);
}
