import React from 'react'

const TIMELINE_DATA = [
    {
        year: 2024, events: [
            { type: 'hazard', label: 'LL97 FIRST CAP (OFFICE)', pos: '10%', width: '15%' },
            { type: 'info', label: 'ELEVATOR CAT 1 DUE', pos: '60%', width: '20%' }
        ]
    },
    {
        year: 2025, events: [
            { type: 'hazard', label: 'LEAD PAINT XRF DEADLINE (AUG 9)', pos: '50%', width: '30%' },
            { type: 'info', label: 'FISP CYCLE 9 FILING ENDS', pos: '20%', width: '25%' }
        ]
    },
    {
        year: 2026, events: [
            { type: 'info', label: 'CONSTRUCTION SUPER BOTTLE-NECK', pos: '0%', width: '100%' },
            { type: 'hazard', label: 'GAS SERVICE LINE INSPECTION', pos: '40%', width: '15%' }
        ]
    },
    {
        year: 2027, events: [
            { type: 'info', label: 'FISP CYCLE 10 OPENS', pos: '10%', width: '20%' }
        ]
    },
    {
        year: 2028, events: [
            { type: 'hazard', label: 'LL157 GAS DETECTOR MANDATE', pos: '30%', width: '10%' }
        ]
    },
]

function Timeline() {
    return (
        <div style={{ background: 'white', padding: '1rem' }}>
            <div style={{ borderBottom: '2px solid black', paddingBottom: '1rem', marginBottom: '2rem' }}>
                <h2 style={{ color: 'var(--color-navy)' }}>RED TAPE TIMELINE</h2>
                <p style={{ fontWeight: 600 }}>2024–2030 REGULATORY ROADMAP FOR NYC HOLDINGS.</p>
            </div>

            <div className="timeline-grid">
                {TIMELINE_DATA.map(row => (
                    <React.Fragment key={row.year}>
                        <div className="timeline-year">{row.year}</div>
                        <div className="timeline-content" style={{ position: 'relative', height: '80px' }}>
                            {row.events.map((e, index) => (
                                <div
                                    key={index}
                                    className={`event-bar ${e.type}`}
                                    style={{
                                        position: 'absolute',
                                        left: e.pos,
                                        width: e.width,
                                        top: `${10 + (index * 35)}px`
                                    }}
                                >
                                    {e.label}
                                </div>
                            ))}
                        </div>
                    </React.Fragment>
                ))}
            </div>

            <div style={{ marginTop: '2rem', display: 'flex', gap: '2rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', fontWeight: 800 }}>
                    <div style={{ width: 12, height: 12, background: 'var(--color-red)' }}></div> CRITICAL DEADLINE
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', fontWeight: 800 }}>
                    <div style={{ width: 12, height: 12, background: 'var(--color-navy)' }}></div> COMPLIANCE FILING
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', fontWeight: 800 }}>
                    <div style={{ width: 12, height: 12, background: 'var(--color-green)' }}></div> GENERAL MANDATE
                </div>
            </div>
        </div>
    )
}

export default Timeline
