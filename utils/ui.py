import streamlit as st

def apply_role_based_sidebar():
    """Hides sidebar pages based on the user's role using CSS + JS."""
    if "role" not in st.session_state:
        return
        
    if st.session_state.role == "user":
        # Hide Admin Portal from users
        st.markdown("""
        <style>
            [data-testid="stSidebarNav"] a[href*="Admin_Portal"] { display: none !important; }
            [data-testid="stSidebarNav"] li:has(a[href*="Admin_Portal"]) { display: none !important; }
            [data-testid="stSidebarNav"] a[href*="Admin"] { display: none !important; }
            [data-testid="stSidebarNav"] li:has(a[href*="Admin"]) { display: none !important; }
            [data-testid="stSidebarNav"] ul li:last-child { display: none !important; }
            [data-testid="stSidebarNavItems"] a[href*="Admin"] { display: none !important; }
            [data-testid="stSidebarNavItems"] li:last-child { display: none !important; }
        </style>
        <script>
        function _hideAdmin() {
            document.querySelectorAll('nav a, [data-testid="stSidebarNav"] a, aside a, [data-testid="stSidebarNavItems"] a, section[data-testid="stSidebar"] a').forEach(function(a) {
                if (a.textContent && a.textContent.trim().indexOf('Admin') !== -1) {
                    a.style.display = 'none';
                    if (a.parentElement && a.parentElement.tagName === 'LI') {
                        a.parentElement.style.display = 'none';
                    }
                    if (a.closest && a.closest('li')) {
                        a.closest('li').style.display = 'none';
                    }
                }
            });
        }
        _hideAdmin();
        setInterval(_hideAdmin, 500);
        new MutationObserver(_hideAdmin).observe(document.body, {childList: true, subtree: true});
        </script>
        """, unsafe_allow_html=True)

    elif st.session_state.role == "admin":
        # Hide user pages from admin
        st.markdown("""
        <style>
            [data-testid="stSidebarNav"] a[href*="Clinician"] { display: none !important; }
            [data-testid="stSidebarNav"] a[href*="Psychiatrist"] { display: none !important; }
            [data-testid="stSidebarNav"] a[href*="Previous"] { display: none !important; }
            [data-testid="stSidebarNav"] li:has(a[href*="Clinician"]) { display: none !important; }
            [data-testid="stSidebarNav"] li:has(a[href*="Psychiatrist"]) { display: none !important; }
            [data-testid="stSidebarNav"] li:has(a[href*="Previous"]) { display: none !important; }
            [data-testid="stSidebarNavItems"] a[href*="Clinician"] { display: none !important; }
            [data-testid="stSidebarNavItems"] a[href*="Psychiatrist"] { display: none !important; }
            [data-testid="stSidebarNavItems"] a[href*="Previous"] { display: none !important; }
        </style>
        <script>
        function _hideUserPages() {
            document.querySelectorAll('nav a, [data-testid="stSidebarNav"] a, aside a, [data-testid="stSidebarNavItems"] a, section[data-testid="stSidebar"] a').forEach(function(a) {
                var t = a.textContent ? a.textContent.trim() : '';
                if (t.indexOf('Clinician') !== -1 || t.indexOf('Psychiatrist') !== -1 || t.indexOf('Previous') !== -1) {
                    a.style.display = 'none';
                    if (a.parentElement && a.parentElement.tagName === 'LI') {
                        a.parentElement.style.display = 'none';
                    }
                    if (a.closest && a.closest('li')) {
                        a.closest('li').style.display = 'none';
                    }
                }
            });
        }
        _hideUserPages();
        setInterval(_hideUserPages, 500);
        new MutationObserver(_hideUserPages).observe(document.body, {childList: true, subtree: true});
        </script>
        """, unsafe_allow_html=True)
