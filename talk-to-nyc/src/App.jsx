import React, { useState } from 'react'
import Chat from './components/Chat'
import Poker from './components/Poker'
import Timeline from './components/Timeline'

function App() {
    const [activeTab, setActiveTab] = useState('chat')
    const [groundWithSearch, setGroundWithSearch] = useState(false)
    const [sources, setSources] = useState({
        charter: true,
        adminCode: true,
        rules: true
    })

    const toggleSource = (source) => {
        setSources(prev => ({ ...prev, [source]: !prev[source] }))
    }

    return (
        <div className="container">
            <header>
                <div>
                    <a href="/" className="brand">Talk to NYC</a>
                    <p style={{ fontWeight: 600, fontSize: '0.75rem', marginTop: '0.5rem' }}>
                        REGULATORY INTELLIGENCE / EST. 2026
                    </p>
                </div>
                <nav>
                    <a
                        href="#"
                        className={activeTab === 'chat' ? 'active' : ''}
                        onClick={() => setActiveTab('chat')}
                    >
                        01. Can I Do This?
                    </a>
                    <a
                        href="#"
                        className={activeTab === 'poker' ? 'active' : ''}
                        onClick={() => setActiveTab('poker')}
                    >
                        02. Penalty Poker
                    </a>
                    <a
                        href="#"
                        className={activeTab === 'timeline' ? 'active' : ''}
                        onClick={() => setActiveTab('timeline')}
                    >
                        03. Red Tape Timeline
                    </a>
                </nav>
            </header>

            <section style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <span style={{ fontWeight: 800, fontSize: '0.75rem' }}>FILTER SOURCES:</span>
                    {Object.keys(sources).map(key => (
                        <button
                            key={key}
                            onClick={() => toggleSource(key)}
                            style={{
                                background: sources[key] ? 'var(--color-black)' : 'transparent',
                                color: sources[key] ? 'white' : 'var(--color-black)',
                                border: '1px solid var(--color-black)',
                                padding: '0.25rem 0.75rem',
                                fontSize: '0.7rem',
                                fontWeight: 600,
                                textTransform: 'uppercase',
                                cursor: 'pointer'
                            }}
                        >
                            {key}
                        </button>
                    ))}
                </div>

                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <label style={{ fontWeight: 800, fontSize: '0.75rem', cursor: 'pointer' }}>
                        <input
                            type="checkbox"
                            checked={groundWithSearch}
                            onChange={() => setGroundWithSearch(!groundWithSearch)}
                            style={{ marginRight: '0.5rem' }}
                        />
                        GROUND WITH GOOGLE SEARCH
                    </label>
                </div>
            </section>

            <main>
                {activeTab === 'chat' && <Chat sources={sources} search={groundWithSearch} />}
                {activeTab === 'poker' && <Poker />}
                {activeTab === 'timeline' && <Timeline />}
            </main>

            <footer style={{ marginTop: '4rem', padding: '2rem 0', borderTop: '2px solid black', fontSize: '0.75rem', opacity: 0.6 }}>
                <p>&copy; 2026 FALSE DAWN INDUSTRIES / DATA DERIVED FROM NYC CHARTER, ADMIN CODE, AND RULES.</p>
                <p>NOT LEGAL ADVICE. FOR INFORMATION PURPOSES ONLY.</p>
            </footer>
        </div>
    )
}

export default App
