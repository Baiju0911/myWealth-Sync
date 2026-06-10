// frontend/src/layouts/MainLayout.tsx
import React, { useState } from 'react';
import DashboardView from '../views/BanksView.tsx';

// 🔌 Type declarations for tracking active view ports
type ViewState = 'dashboard' | 'accounts' | 'credentials' | 'schemas';

const MainLayout: React.FC = () => {
    const [currentView, setCurrentView] = useState<ViewState>('dashboard');

    // 🗺️ Render helper to swap views based on active state navigation
    const renderContent = () => {
        switch (currentView) {
            case 'dashboard':
                return <DashboardView />;
            case 'accounts':
                return (
                    <div style={styles.fallbackCard}>
                        <h2>Accounts Registry Matrix</h2>
                        <p>This layout view will hook into your <code>/api/accounts/</code> endpoints to map individual user ledger branches.</p>
                    </div>
                );
            case 'credentials':
                return (
                    <div style={styles.fallbackCard}>
                        <h2>Secure Statement Password Keys Vault</h2>
                        <p>This layout view will manage access keys to map decryption passes for uploaded statement documents.</p>
                    </div>
                );
            default:
                return <DashboardView />;
        }
    };

    return (
        <div style={styles.appWrapper}>
            {/* 🧭 1. Left Fixed Sidebar Navigation Panel */}
            <aside style={styles.sidebar}>
                <div style={styles.brandContainer}>
                    <div style={styles.brandIcon}>W</div>
                    <span style={styles.brandName}>myWealth Sync</span>
                </div>
                
                <nav style={styles.navigationStack}>
                    <button 
                        onClick={() => setCurrentView('dashboard')} 
                        style={{ ...styles.navLink, ...(currentView === 'dashboard' ? styles.navLinkActive : {}) }}
                    >
                        📊 System Dashboard
                    </button>
                    
                    <button 
                        onClick={() => setCurrentView('accounts')} 
                        style={{ ...styles.navLink, ...(currentView === 'accounts' ? styles.navLinkActive : {}) }}
                    >
                        🏦 Ledger Accounts
                    </button>
                    
                    <button 
                        onClick={() => setCurrentView('credentials')} 
                        style={{ ...styles.navLink, ...(currentView === 'credentials' ? styles.navLinkActive : {}) }}
                    >
                        🔐 Password Vault
                    </button>
                </nav>

                <div style={styles.sidebarFooter}>
                    <small>System Environment: Dev</small>
                </div>
            </aside>

            {/* 💻 2. Right Scrollable Main Content Canvas Viewport */}
            <main style={styles.contentCanvas}>
                {renderContent()}
            </main>
        </div>
    );
};

// 🎨 Clean, production layout CSS style configuration matrices

const styles: { [key: string]: React.CSSProperties } = {
    appWrapper: { 
        display: 'flex', 
        minHeight: '100vh', 
        width: '100vw', 
        backgroundColor: '#f8f9fa', 
        overflow: 'hidden', 
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' 
    },
    sidebar: { 
        width: '260px', 
        backgroundColor: '#1e293b', 
        color: '#f8fafc', 
        display: 'flex', 
        flexDirection: 'column', 
        padding: '24px 16px', 
        // 🛡️ FIXED: Swapped 'boxDelta' to standard 'boxShadow'
        boxShadow: '4px 0 10px rgba(0,0,0,0.05)', 
        // 🛡️ FIXED: Swapped 'shrink' to strict 'flexShrink'
        flexShrink: 0 
    },
    brandContainer: { display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '40px', paddingLeft: '8px' },
    brandIcon: { width: '32px', height: '32px', backgroundColor: '#3b82f6', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold', fontSize: '16px', color: '#fff' },
    brandName: { fontSize: '18px', fontWeight: '700', letterSpacing: '-0.5px' },
    navigationStack: { display: 'flex', flexDirection: 'column', gap: '8px', flexGrow: 1 },
    navLink: { display: 'block', width: '100%', textAlign: 'left', backgroundColor: 'transparent' } // Sanitized end block snippet
};


export default MainLayout;