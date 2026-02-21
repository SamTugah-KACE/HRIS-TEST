import React, { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search, Filter, ChevronLeft, ChevronRight, Eye, Download, UserPlus, RefreshCw, MoreHorizontal, Mail } from 'lucide-react';
import { getEmployees, type EmployeeListResponse } from '../api/hrisCoreClient';
import { useAuth } from '../auth/AuthProvider';
import { isManagerRole, HRIS_ROLES } from '../auth/roles';
import { clsx } from 'clsx';

export const EmployeeListPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const role = user?.effectiveRole ?? HRIS_ROLES.EMPLOYEE;

  useEffect(() => {
    if (!isManagerRole(role)) {
      navigate('/profile', { replace: true });
    }
  }, [role, navigate]);

  const [data, setData] = useState<EmployeeListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');
  const [departmentFilter, setDepartmentFilter] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getEmployees({ search, status: statusFilter, department: departmentFilter, page, page_size: 10 });
      setData(result);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter, departmentFilter, page]);

  useEffect(() => { void load(); }, [load]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    void load();
  };

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (!data) return;
    if (selected.size === data.employees.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(data.employees.map(e => e.employee_id)));
    }
  };

  if (!isManagerRole(role)) return null;

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed right-4 top-20 z-50 flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-medium text-white shadow-lg">
          <Eye className="h-4 w-4" /> {toast}
        </div>
      )}

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Staff Records</h1>
          <p className="mt-1 text-sm text-gray-500">Browse and manage employee records from SRMS</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => showToast('Add employee form would open here')} className="btn-primary">
            <UserPlus className="h-4 w-4" /> Add Employee
          </button>
          <button onClick={() => showToast('Exporting employee data...')} className="btn-secondary">
            <Download className="h-4 w-4" /> Export
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="card">
        <form onSubmit={handleSearch} className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label htmlFor="search" className="mb-1 block text-sm font-medium text-gray-700">Search</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                id="search"
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search by name, staff ID, or email..."
                className="input-field pl-10"
              />
            </div>
          </div>
          <div className="w-full sm:w-40">
            <label htmlFor="dept" className="mb-1 block text-sm font-medium text-gray-700">Department</label>
            <select id="dept" value={departmentFilter} onChange={e => { setDepartmentFilter(e.target.value); setPage(1); }} className="input-field">
              <option value="">All Departments</option>
              <option value="Information Technology">Information Technology</option>
              <option value="Human Resources">Human Resources</option>
              <option value="Finance">Finance</option>
              <option value="Administration">Administration</option>
              <option value="Legal">Legal</option>
            </select>
          </div>
          <div className="w-full sm:w-32">
            <label htmlFor="status" className="mb-1 block text-sm font-medium text-gray-700">Status</label>
            <select id="status" value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }} className="input-field">
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
          <button type="submit" className="btn-primary">
            <Filter className="h-4 w-4" /> Filter
          </button>
          <button type="button" onClick={() => { setSearch(''); setStatusFilter('active'); setDepartmentFilter(''); setPage(1); }} className="btn-secondary">
            <RefreshCw className="h-4 w-4" /> Reset
          </button>
        </form>
      </div>

      {/* Bulk Actions */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 rounded-lg bg-brand-500/10 px-4 py-3">
          <span className="text-sm font-medium text-brand-600">{selected.size} selected</span>
          <div className="h-4 w-px bg-brand-500/30" />
          <button onClick={() => showToast(`Sending email to ${selected.size} employees...`)} className="flex items-center gap-1 text-sm font-medium text-brand-600 hover:text-brand-700">
            <Mail className="h-3.5 w-3.5" /> Send Email
          </button>
          <button onClick={() => showToast(`Exporting ${selected.size} records...`)} className="flex items-center gap-1 text-sm font-medium text-brand-600 hover:text-brand-700">
            <Download className="h-3.5 w-3.5" /> Export Selected
          </button>
          <button onClick={() => setSelected(new Set())} className="ml-auto text-xs text-gray-500 hover:text-gray-700">Clear selection</button>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-gray-200 bg-gray-50">
              <tr>
                <th className="px-4 py-3">
                  <input type="checkbox" checked={data ? selected.size === data.employees.length && data.employees.length > 0 : false} onChange={toggleSelectAll} className="h-4 w-4 rounded border-gray-300" />
                </th>
                <th className="px-4 py-3 font-medium text-gray-500">Employee</th>
                <th className="px-4 py-3 font-medium text-gray-500">Staff ID</th>
                <th className="px-4 py-3 font-medium text-gray-500">Department</th>
                <th className="px-4 py-3 font-medium text-gray-500">Branch</th>
                <th className="px-4 py-3 font-medium text-gray-500">Status</th>
                <th className="px-4 py-3 font-medium text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-gray-400">
                    <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-brand-500" />
                  </td>
                </tr>
              ) : !data || data.employees.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-gray-400">No employees found.</td>
                </tr>
              ) : (
                data.employees.map(emp => (
                  <tr key={emp.employee_id} className={clsx('hover:bg-gray-50 cursor-pointer', selected.has(emp.employee_id) && 'bg-brand-500/5')}>
                    <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                      <input type="checkbox" checked={selected.has(emp.employee_id)} onChange={() => toggleSelect(emp.employee_id)} className="h-4 w-4 rounded border-gray-300" />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <Link to={`/employees/${emp.employee_id}`} className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-500/10 text-xs font-bold text-brand-600">
                          {emp.full_name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                        </div>
                        <div>
                          <p className="font-medium text-gray-900">{emp.full_name}</p>
                          <p className="text-xs text-gray-500">{emp.email}</p>
                        </div>
                      </Link>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-gray-600">{emp.staff_id}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-500">{emp.department}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-500">{emp.branch}</td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <span className={clsx(
                        'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                        emp.status === 'Active' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-600'
                      )}>
                        {emp.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <div className="flex items-center gap-1">
                        <Link to={`/employees/${emp.employee_id}`} className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-brand-500" title="View 360 Profile">
                          <Eye className="h-4 w-4" />
                        </Link>
                        <button onClick={() => showToast(`Sending email to ${emp.full_name}...`)} className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-brand-500" title="Send Email">
                          <Mail className="h-4 w-4" />
                        </button>
                        <button onClick={() => showToast(`More options for ${emp.full_name}`)} className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100" title="More">
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {data && (
          <div className="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-4 py-3">
            <p className="text-sm text-gray-500">
              Showing {((data.page - 1) * 10) + 1}-{Math.min(data.page * 10, data.total)} of {data.total} employees
            </p>
            <div className="flex gap-2">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="btn-secondary py-1.5 text-xs disabled:opacity-50">
                <ChevronLeft className="h-4 w-4" /> Prev
              </button>
              {Array.from({ length: Math.min(data.total_pages, 5) }, (_, i) => i + 1).map(p => (
                <button key={p} onClick={() => setPage(p)} className={clsx('rounded-lg px-3 py-1.5 text-xs font-medium', p === page ? 'bg-brand-500 text-white' : 'text-gray-600 hover:bg-gray-100')}>
                  {p}
                </button>
              ))}
              <button onClick={() => setPage(p => Math.min(data.total_pages, p + 1))} disabled={page >= data.total_pages} className="btn-secondary py-1.5 text-xs disabled:opacity-50">
                Next <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
