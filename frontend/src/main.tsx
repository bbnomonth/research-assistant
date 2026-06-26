import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider, App as AntdApp, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';
import './styles/global.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#2f54eb',
          borderRadius: 6,
          fontSize: 14,
        },
      }}
    >
      <AntdApp>
        <RouterProvider
          router={router}
          future={{ v7_startTransition: true }}
        />
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
);
