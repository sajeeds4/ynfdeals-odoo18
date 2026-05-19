/**
 * DataTable — styled sortable table with column definitions.
 */
export default function DataTable({ columns, rows, emptyText = 'No data', maxHeight = '50vh', onRowClick }) {
  return (
    <div className="data-table__wrapper" style={{ maxHeight }}>
      <table className="data-table">
        <thead>
          <tr>
            {columns.map(col => (
              <th key={col.key} style={col.width ? { width: col.width } : undefined} className={col.align === 'right' ? 'text-right' : ''}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(!rows || rows.length === 0) ? (
            <tr><td colSpan={columns.length} className="data-table__empty">{emptyText}</td></tr>
          ) : (
            rows.map((row, i) => (
              <tr key={row.id || i} onClick={() => onRowClick?.(row)} className={onRowClick ? 'clickable' : ''}>
                {columns.map(col => (
                  <td key={col.key} className={col.align === 'right' ? 'text-right' : ''}>
                    {col.render ? col.render(row[col.key], row) : (row[col.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
